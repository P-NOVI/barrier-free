"""혼잡도 예측 모델을 학습·평가하고 저장한다.

실행: ml/ 에서 uv run python -m congestion.train
- 입력: pipeline 13 단계 학습셋(interim/training/hourly.parquet)과 sensor_scale.json
- 출력(저장소 models/): congestion_model.txt(LightGBM), congestion_meta.json(피처 목록,
  범주 목록, 센서별 정규화 기준값, 학습 기간, 지표), congestion_eval.json(평가 보고서)
순서
1. baseline: 센서·요일·시각별 중앙값(평균도 같이 잰다).
2. 목적함수(cross_entropy, L1, L2)마다 같은 피처로 학습해 검증 구간 MAE 가 가장
   낮은 것을 고른다. 테스트 구간은 고르는 데 쓰지 않고 보고만 한다.
3. 고른 목적함수로 날씨 제외, 공휴일 제외 모델을 학습해 기여를 비교한다.
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

from congestion import baseline, metrics
from congestion.common import CONFIG_PATH, data_path, load_config, repo_path
from congestion.data import (
    Columns,
    build_features,
    load_columns,
    make_vocab,
    split_masks,
    take,
)

FULL_GROUPS = ["base", "weather", "holiday"]
ABLATIONS = {
    "no_weather": ["base", "holiday"],
    "no_holiday": ["base", "weather"],
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
    """0~1 로 자른 예측. cross_entropy 는 이미 확률이지만 L1·L2 는 넘칠 수 있다."""
    return np.clip(
        booster.predict(matrix, num_iteration=booster.best_iteration), 0.0, 1.0
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
        (matrices["train"], parts["train"]["congestion"]),
        (matrices["valid"], parts["valid"]["congestion"]),
        names,
        config["features"]["categorical"],
        config["model"],
    )
    valid_pred = predict(booster, matrices["valid"])
    test_pred = predict(booster, matrices["test"])
    return Trained(
        booster=booster,
        names=names,
        valid=metrics.scores(parts["valid"]["congestion"], valid_pred),
        test=metrics.scores(parts["test"]["congestion"], test_pred),
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
        for name in ("sensor_code", "day_of_week", "hour_of_day", "congestion")
    }
    for statistic in baseline.STATISTICS:
        result[statistic] = {}
        for split, source in (("valid", parts["train"]), ("test", pooled)):
            keys = baseline.slot_keys(
                source["sensor_code"], source["day_of_week"], source["hour_of_day"]
            )
            by_slot, by_sensor = baseline.fit_baseline(
                keys, source["sensor_code"], source["congestion"], statistic
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
            result[statistic][split] = metrics.scores(target["congestion"], pred)
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
    y = test["congestion"]
    by_sensor = metrics.grouped_mae(test["sensor_code"], y, pred, base_pred)
    ranked = sorted(
        (item for item in by_sensor.items() if item[1]["rows"] >= LOW_ROWS),
        key=lambda item: item[1]["model_mae"],
        reverse=True,
    )
    model_maes = np.array([item["model_mae"] for item in by_sensor.values()])
    return {
        "by_hour": metrics.grouped_mae(test["hour_of_day"], y, pred, base_pred),
        "by_day_type": metrics.grouped_mae(day_type(test), y, pred, base_pred),
        "by_rain": metrics.grouped_mae(rain_kind(test), y, pred, base_pred),
        "sensor_mae_median": round(float(np.median(model_maes)), 5),
        "worst_sensors": dict(ranked[:worst_sensors]),
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
    masks = split_masks(columns["slot_start"], config["split"])
    parts = {name: take(columns, mask) for name, mask in masks.items()}
    vocab = make_vocab(columns, config["features"]["categorical"])
    print(
        "행 "
        + ", ".join(
            f"{name} {part['congestion'].size:,}" for name, part in parts.items()
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
    scale = json.loads(data_path(data["sensor_scale"]).read_text(encoding="utf-8"))
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
        "target_quantile": scale["quantile"],
        "scale_train_start": scale["train_start"],
        "scale_train_end": scale["train_end"],
        "sensor_scale": scale["scales"],
    }
    write_json(model_dir / data["meta_file"], meta)
    write_json(model_dir / data["eval_file"], evaluation)
    print(
        f"선택 {best}, 테스트 MAE {final.test['mae']} (baseline {base_test['mae']}) "
        f"→ {model_dir} ({time.time() - started:.0f}s)",
        flush=True,
    )


if __name__ == "__main__":
    main()
