"""유동인구 예측 모델을 학습·평가하고 저장한다.

실행: ml/ 에서 uv run python -m foot_traffic.train
- 입력: pipeline 13 단계 학습셋(interim/training/hourly.parquet)
- 타깃: foot_traffic, 한 시간에 센서를 지나간 사람 수(명/시간). 정규화하지 않는다.
- 출력(저장소 models/): foot_traffic_model.txt(LightGBM), foot_traffic_meta.json(피처
  목록, 범주 목록, 학습 기간, 지표), foot_traffic_eval.json(평가 보고서)
- 오차는 사람 수(MAE, RMSE)와 오차율(오차 합 / 실제 합)로 잰다. 센서마다 규모가 크게
  달라 사람 수 오차는 붐비는 센서가 좌우하므로 오차율도 같이 본다.
순서
1. baseline: 센서·요일·시각별 중앙값(평균도 같이 잰다).
2. 목적함수(L1, L2, poisson)마다 같은 피처로 학습해 검증 구간 MAE 가 가장
   낮은 것을 고른다. 테스트 구간은 고르는 데 쓰지 않고 보고만 한다.
3. 고른 목적함수로 날씨 제외, 공휴일 제외, 쉬는 날 전후 제외 모델을 학습해 기여를
   비교한다.
4. 고른 모델의 테스트 구간 오차를 시각·요일 종류·강수·센서별로 나눠 보고한다.
"""

import argparse
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

from foot_traffic import baseline, metrics
from foot_traffic.common import CONFIG_PATH, data_path, load_config, repo_path
from foot_traffic.data import (
    Columns,
    add_off_adjacent,
    build_features,
    load_columns,
    make_vocab,
    split_masks,
    take,
)

FULL_GROUPS = ["base", "weather", "holiday", "off_adjacent"]
ABLATIONS = {
    "no_weather": ["base", "holiday", "off_adjacent"],
    "no_holiday": ["base", "weather"],
    "no_off_adjacent": ["base", "weather", "holiday"],
}
LOW_ROWS = 1  # 센서별 오차에 넣는 최소 행 수
IMPORTANCE_DIGITS = 4


@dataclass
class Trained:
    booster: lgb.Booster
    names: list[str]
    valid: dict[str, float]
    test: dict[str, float]
    test_pred: np.ndarray


def train_model(
    objective: str,
    train: tuple[np.ndarray, np.ndarray],
    valid: tuple[np.ndarray, np.ndarray],
    names: list[str],
    categorical: list[str],
    model_config: dict[str, Any],
) -> lgb.Booster:
    """조기 종료는 검증 구간 MAE(l1)로 한다. 목적함수가 달라도 같은 기준이다."""
    params = {
        **model_config["params"],
        "objective": objective,
        "metric": "l1",
        "seed": model_config["seed"],
    }
    train_set = lgb.Dataset(
        train[0],
        train[1],
        feature_name=names,
        categorical_feature=[n for n in categorical if n in names],
    )
    valid_set = lgb.Dataset(valid[0], valid[1], reference=train_set)
    return lgb.train(
        params,
        train_set,
        num_boost_round=model_config["num_boost_round"],
        valid_sets=[valid_set],
        callbacks=[
            lgb.early_stopping(model_config["early_stopping_rounds"], verbose=False)
        ],
    )


def predict(booster: lgb.Booster, matrix: np.ndarray) -> np.ndarray:
    """0 이상으로 자른 예측(명/시간). L1·L2 는 음수가 나올 수 있다."""
    return np.clip(
        booster.predict(matrix, num_iteration=booster.best_iteration), 0.0, None
    )


def fit_and_score(
    objective: str,
    groups: list[str],
    parts: dict[str, Columns],
    vocab: dict[str, list[Any]],
    config: dict[str, Any],
) -> Trained:
    matrices = {}
    for split, part in parts.items():
        matrices[split], names = build_features(part, vocab, config["features"], groups)
    booster = train_model(
        objective,
        (matrices["train"], parts["train"]["foot_traffic"]),
        (matrices["valid"], parts["valid"]["foot_traffic"]),
        names,
        config["features"]["categorical"],
        config["model"],
    )
    valid_pred = predict(booster, matrices["valid"])
    test_pred = predict(booster, matrices["test"])
    return Trained(
        booster=booster,
        names=names,
        valid=metrics.scores(parts["valid"]["foot_traffic"], valid_pred),
        test=metrics.scores(parts["test"]["foot_traffic"], test_pred),
        test_pred=test_pred,
    )


def summarize(trained: Trained, base_test: dict[str, float]) -> dict[str, Any]:
    return {
        "best_iteration": trained.booster.best_iteration,
        "valid": trained.valid,
        "test": trained.test,
        "test_mae_improvement": metrics.improvement(
            base_test["mae"], trained.test["mae"]
        ),
    }


def run_baselines(parts: dict[str, Columns]) -> dict[str, Any]:
    """검증 구간은 학습 구간으로, 테스트 구간은 학습+검증 구간으로 만든 baseline."""
    result: dict[str, Any] = {}
    predictions: dict[str, np.ndarray] = {}
    pooled = {
        name: np.concatenate([parts["train"][name], parts["valid"][name]])
        for name in ("sensor_code", "day_of_week", "hour_of_day", "foot_traffic")
    }
    for statistic in baseline.STATISTICS:
        result[statistic] = {}
        for split, source in (("valid", parts["train"]), ("test", pooled)):
            keys = baseline.slot_keys(
                source["sensor_code"], source["day_of_week"], source["hour_of_day"]
            )
            by_slot, by_sensor = baseline.fit_baseline(
                keys, source["sensor_code"], source["foot_traffic"], statistic
            )
            target = parts[split]
            pred = baseline.predict_baseline(
                baseline.slot_keys(
                    target["sensor_code"], target["day_of_week"], target["hour_of_day"]
                ),
                target["sensor_code"],
                by_slot,
                by_sensor,
            )
            result[statistic][split] = metrics.scores(target["foot_traffic"], pred)
            predictions[f"{statistic}_{split}"] = pred
    result["predictions"] = predictions
    return result


def day_type(part: Columns) -> np.ndarray:
    """공휴일 / 주말(공휴일 아닌 쉬는 날) / 평일."""
    return np.where(
        part["is_holiday"] == 1,
        "holiday",
        np.where(part["is_off_day"] == 1, "weekend", "weekday"),
    )


def rain_kind(part: Columns) -> np.ndarray:
    rain = part["rain_mm"]
    return np.where(np.isnan(rain), "unknown", np.where(rain > 0, "rain", "no_rain"))


def breakdown(
    test: Columns,
    pred: np.ndarray,
    base_pred: np.ndarray,
    worst_sensors: int,
) -> dict[str, Any]:
    y = test["foot_traffic"]
    by_sensor = metrics.grouped_mae(test["sensor_code"], y, pred, base_pred)
    eligible = [item for item in by_sensor.items() if item[1]["rows"] >= LOW_ROWS]
    by_people = sorted(eligible, key=lambda item: item[1]["model_mae"], reverse=True)
    by_rate = sorted(
        eligible, key=lambda item: item[1]["model_error_rate"], reverse=True
    )
    model_maes = np.array([item["model_mae"] for item in by_sensor.values()])
    model_rates = np.array([item["model_error_rate"] for item in by_sensor.values()])
    return {
        "by_hour": metrics.grouped_mae(test["hour_of_day"], y, pred, base_pred),
        "by_day_type": metrics.grouped_mae(day_type(test), y, pred, base_pred),
        "by_rain": metrics.grouped_mae(rain_kind(test), y, pred, base_pred),
        "sensor_mae_median": round(float(np.median(model_maes)), 2),
        "sensor_error_rate_median": round(float(np.median(model_rates)), 4),
        "worst_sensors_by_people": dict(by_people[:worst_sensors]),
        "worst_sensors_by_error_rate": dict(by_rate[:worst_sensors]),
    }


def importance(trained: Trained) -> dict[str, float]:
    gain = trained.booster.feature_importance("gain")
    share = gain / gain.sum()
    pairs = sorted(zip(trained.names, share), key=lambda p: p[1], reverse=True)
    return {name: round(float(value), IMPORTANCE_DIGITS) for name, value in pairs}


def write_json(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(content, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)
    started = time.time()

    columns = load_columns(data_path(config["data"]["training_set"]))
    add_off_adjacent(columns, data_path(config["data"]["calendar"]))
    masks = split_masks(columns["slot_start"], config["split"])
    parts = {name: take(columns, mask) for name, mask in masks.items()}
    vocab = make_vocab(columns, config["features"]["categorical"])
    print(
        "행 "
        + ", ".join(
            f"{name} {part['foot_traffic'].size:,}" for name, part in parts.items()
        ),
        flush=True,
    )

    base = run_baselines(parts)
    predictions = base.pop("predictions")
    base_test = base["median"]["test"]
    print(f"baseline(중앙값) 테스트 {base_test}", flush=True)

    objectives = {}
    trained: dict[str, Trained] = {}
    for objective in config["model"]["objectives"]:
        trained[objective] = fit_and_score(objective, FULL_GROUPS, parts, vocab, config)
        objectives[objective] = summarize(trained[objective], base_test)
        print(f"{objective}: {objectives[objective]}", flush=True)
    best = min(trained, key=lambda name: trained[name].valid["mae"])

    ablation = {"full": objectives[best]}
    for label, groups in ABLATIONS.items():
        result = fit_and_score(best, groups, parts, vocab, config)
        ablation[label] = summarize(result, base_test)
        print(f"{label}: {ablation[label]}", flush=True)

    final = trained[best]
    evaluation = {
        "baseline": base,
        "objectives": objectives,
        "selected_objective": best,
        "ablation": ablation,
        "importance": importance(final),
        "breakdown": breakdown(
            parts["test"],
            final.test_pred,
            predictions["median_test"],
            config["report"]["worst_sensors"],
        ),
    }

    data = config["data"]
    model_dir = repo_path(data["model_dir"])
    model_dir.mkdir(parents=True, exist_ok=True)
    final.booster.save_model(
        str(model_dir / data["model_file"]), num_iteration=final.booster.best_iteration
    )
    train_slots = parts["train"]["slot_start"]
    meta = {
        "created": date.today().isoformat(),
        "lightgbm": lgb.__version__,
        "objective": best,
        "best_iteration": final.booster.best_iteration,
        "feature_names": final.names,
        "categorical_features": [
            n for n in config["features"]["categorical"] if n in final.names
        ],
        "vocab": vocab,
        "temp_bin_c": config["features"]["temp_bin_c"],
        "rain_bins_mm": config["features"]["rain_bins_mm"],
        "split": config["split"],
        "train_first_slot": str(train_slots.min()),
        "train_last_slot": str(train_slots.max()),
        "valid": final.valid,
        "test": final.test,
        "baseline_test": base_test,
        "target": "foot_traffic",
        "unit": "명/시간",
    }
    write_json(model_dir / data["meta_file"], meta)
    write_json(model_dir / data["eval_file"], evaluation)
    print(
        f"선택 {best}, 테스트 MAE {final.test['mae']}명 "
        f"(baseline {base_test['mae']}명) "
        f"→ {model_dir} ({time.time() - started:.0f}s)",
        flush=True,
    )


if __name__ == "__main__":
    main()
