"""유동인구 예측 모델을 학습·평가하고 저장한다.

실행: ml/ 에서 uv run python -m foot_traffic.train
- 입력: pipeline 13 단계 학습셋(interim/training/hourly.parquet)
- 타깃: foot_traffic, 한 시간에 센서를 지나간 사람 수(명/시간). 정규화하지 않는다.
- 출력(저장소 models/): foot_traffic_model.txt(LightGBM), foot_traffic_meta.json(피처
  목록, 범주 목록, 학습 기간, 지표), foot_traffic_eval.json(평가 보고서)
- 오차는 사람 수(MAE, RMSE)와 오차율(오차 합 / 실제 합)로 잰다. 센서마다 규모가 크게
  달라 사람 수 오차는 붐비는 센서가 좌우하므로 오차율도 같이 본다.
순서
1. baseline: 센서·요일·시각별 중앙값과 평균. 검증 구간 MAE 가 낮은 쪽을 기준 baseline
   으로 삼아 모델 개선율과 구분별 비교에 쓴다.
2. 목적함수(L1, L2, poisson)마다 같은 피처로 학습해 검증 구간 MAE 가 가장
   낮은 것을 고른다. 테스트 구간은 고르는 데 쓰지 않고 보고만 한다.
3. 고른 목적함수로 날씨 제외, 공휴일 제외, 쉬는 날 전후 제외 모델을 학습해 기여를
   비교한다(--skip-ablation 이면 건너뛴다. 최종 모델에는 영향이 없다).
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
    add_recent_levels,
    build_features,
    load_columns,
    make_vocab,
    split_masks,
    take,
)

FULL_GROUPS = ["base", "weather", "holiday", "off_adjacent", "recent_level"]
ABLATIONS = {
    "no_weather": ["base", "holiday", "off_adjacent", "recent_level"],
    "no_holiday": ["base", "weather", "recent_level"],
    "no_off_adjacent": ["base", "weather", "holiday", "recent_level"],
    "no_recent_level": ["base", "weather", "holiday", "off_adjacent"],
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
    train: tuple[np.ndarray, np.ndarray, np.ndarray | None],
    valid: tuple[np.ndarray, np.ndarray, np.ndarray | None],
    names: list[str],
    categorical: list[str],
    model_config: dict[str, Any],
) -> lgb.Booster:
    """조기 종료는 검증 구간 MAE(l1)로 한다. 목적함수가 달라도 같은 기준이다.

    train·valid 는 (피처, 타깃, 가중치 또는 None)이다. 가중치를 주면 검증 MAE 도 그
    가중치로 잰다.
    """
    params = {
        **model_config["params"],
        "objective": objective,
        "metric": "l1",
        "seed": model_config["seed"],
    }
    train_set = lgb.Dataset(
        train[0],
        train[1],
        weight=train[2],
        feature_name=names,
        categorical_feature=[n for n in categorical if n in names],
    )
    valid_set = lgb.Dataset(valid[0], valid[1], weight=valid[2], reference=train_set)
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


def reference_levels(
    parts: dict[str, Columns],
    predictions: dict[str, np.ndarray],
    target_config: dict[str, Any],
) -> dict[str, np.ndarray]:
    """분할마다 타깃을 나누는 기준값. 학습 구간은 최근 수준이 없으면 NaN 이다."""
    refs = {}
    for split, part in parts.items():
        nothing = np.full(part["foot_traffic"].size, np.nan)
        fallback = predictions.get(f"median_{split}", nothing)
        refs[split] = baseline.reference_level(part, fallback, target_config)
    return refs


def fit_and_score(
    objective: str,
    groups: list[str],
    parts: dict[str, Columns],
    refs: dict[str, np.ndarray],
    vocab: dict[str, list[Any]],
    config: dict[str, Any],
) -> Trained:
    """타깃은 사람 수 / 기준값이다. 예측은 기준값을 곱해 사람 수로 되돌려 잰다."""
    matrices = {}
    for split, part in parts.items():
        matrices[split], names = build_features(part, vocab, config["features"], groups)
    target = config["target"]

    def dataset(split: str) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        label = parts[split]["foot_traffic"] / refs[split]
        # 가중치 = 기준값 ** weight_power. 1 이면 사람 수 MAE 와 같고, 1 보다 크면
        # 유동인구가 큰 행을 더 중시한다.
        weight = (
            refs[split] ** target["weight_power"] if target["weight"] == "ref" else None
        )
        return matrices[split], label, weight

    booster = train_model(
        objective,
        dataset("train"),
        dataset("valid"),
        names,
        config["features"]["categorical"],
        config["model"],
    )
    valid_pred = predict(booster, matrices["valid"]) * refs["valid"]
    test_pred = predict(booster, matrices["test"]) * refs["test"]
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
    # 최근 수준 baseline: 피처를 그대로 예측으로 쓴다(검증·테스트 모두 같은 규칙).
    result["recent"] = {}
    for split in ("valid", "test"):
        pred = baseline.recent_predict(parts[split], predictions[f"median_{split}"])
        result["recent"][split] = metrics.scores(parts[split]["foot_traffic"], pred)
        predictions[f"recent_{split}"] = pred
    result["predictions"] = predictions
    return result


def pick_reference(base: dict[str, Any]) -> str:
    """모델과 비교할 baseline: 검증 구간 MAE 가 가장 낮은 것(중앙값·평균·최근 수준).

    약한 baseline 과 비교하면 모델이 좋아 보이므로 더 강한 쪽을 기준으로 삼는다.
    """
    return min(base, key=lambda name: base[name]["valid"]["mae"])


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


def level_breakdown(
    key: np.ndarray,
    y: np.ndarray,
    pred: np.ndarray,
    base_pred: np.ndarray,
    bins: list[float],
    top_quantile: float,
) -> dict[str, Any]:
    """key(명/시간) 크기별 오차와 편향. 많이 지나갈 때 모델이 약한지 보려는 것이다.

    bins 는 구간 경계이고 마지막 경계 이상은 한 구간이다. top 은 key 가 상위
    (1 - top_quantile) 비율인 행이다. 편향 = 예측 - 실제 평균.
    주의: key 를 실제 값으로 잡으면 큰 구간은 우연히 큰 행만 모여 어떤 예측이든
    적게 예측한 것처럼 보이고(평균으로의 회귀), 작은 구간은 반대다. 편향·보정 여부는
    key 를 예측값으로 잡은 쪽으로 판단한다.
    """
    index = np.digitize(key, bins)  # bins[i-1] <= key < bins[i] 이면 i
    by_bin = {}
    for i in range(1, len(bins) + 1):
        mask = index == i
        if mask.any():
            label = f"{bins[i - 1]}~{bins[i]}" if i < len(bins) else f"{bins[-1]}+"
            by_bin[label] = metrics.summarize_rows(y[mask], pred[mask], base_pred[mask])
    threshold = float(np.quantile(key, top_quantile))
    top = key >= threshold
    return {
        "bins": by_bin,
        "top": {
            "threshold": round(threshold, 1),
            **metrics.summarize_rows(y[top], pred[top], base_pred[top]),
        },
    }


def breakdown(
    test: Columns,
    pred: np.ndarray,
    base_pred: np.ndarray,
    report_config: dict[str, Any],
) -> dict[str, Any]:
    worst_sensors = report_config["worst_sensors"]
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
        # 실제 값 기준은 평균으로의 회귀 때문에 편향이 왜곡된다. 예측값 기준을 본다.
        "by_level": {
            name: level_breakdown(
                key,
                y,
                pred,
                base_pred,
                report_config["level_bins"],
                report_config["top_quantile"],
            )
            for name, key in (("actual", y), ("predicted", pred))
        },
        "sensor_mae_median": round(float(np.median(model_maes)), 2),
        # 테스트 구간 합이 0인 센서는 오차율이 없어(NaN) 빼고 센다.
        "sensor_error_rate_median": round(float(np.nanmedian(model_rates)), 4),
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
    parser.add_argument(
        "--skip-ablation",
        action="store_true",
        help="피처를 빼서 기여를 비교하는 학습 3개를 건너뛴다(시간이 절반으로 준다)",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    started = time.time()

    columns = load_columns(data_path(config["data"]["training_set"]))
    add_off_adjacent(columns, data_path(config["data"]["calendar"]))
    add_recent_levels(columns, config["recent_level"])
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
    reference = pick_reference(base)
    base_test = base[reference]["test"]
    print(
        f"기준 baseline({baseline.STATISTIC_NAMES[reference]}) 테스트 {base_test}",
        flush=True,
    )

    refs = reference_levels(parts, predictions, config["target"])
    # 최근 수준이 없는 학습 행은 비율을 못 만들어 뺀다(검증·테스트는 fallback 을 쓴다).
    usable = ~np.isnan(refs["train"])
    if not usable.all():
        print(f"최근 수준이 없는 학습 행 {int((~usable).sum()):,}개 제외", flush=True)
        parts["train"] = take(parts["train"], usable)
        refs["train"] = refs["train"][usable]

    objectives = {}
    trained: dict[str, Trained] = {}
    for objective in config["model"]["objectives"]:
        trained[objective] = fit_and_score(
            objective, FULL_GROUPS, parts, refs, vocab, config
        )
        objectives[objective] = summarize(trained[objective], base_test)
        print(f"{objective}: {objectives[objective]}", flush=True)
    best = min(trained, key=lambda name: trained[name].valid["mae"])

    ablation = {"full": objectives[best]}
    for label, groups in {} if args.skip_ablation else ABLATIONS.items():
        result = fit_and_score(best, groups, parts, refs, vocab, config)
        ablation[label] = summarize(result, base_test)
        print(f"{label}: {ablation[label]}", flush=True)

    final = trained[best]
    evaluation = {
        "baseline": base,
        "reference_baseline": reference,
        "objectives": objectives,
        "selected_objective": best,
        "ablation": ablation,
        "importance": importance(final),
        "breakdown": breakdown(
            parts["test"],
            final.test_pred,
            predictions[f"{reference}_test"],
            config["report"],
        ),
    }

    top = evaluation["breakdown"]["by_level"]["predicted"]["top"]
    share = 1 - config["report"]["top_quantile"]
    print(
        f"예측 상위 {share:.0%}(≥{top['threshold']:.0f}명) "
        f"오차율 모델 {top['model_error_rate']:.1%} / baseline "
        f"{top['baseline_error_rate']:.1%}, 편향 모델 {top['model_bias']:+.0f} / "
        f"baseline {top['baseline_bias']:+.0f}명",
        flush=True,
    )

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
        "recent_level": config["recent_level"],
        "target_transform": config["target"],
        "split": config["split"],
        "train_first_slot": str(train_slots.min()),
        "train_last_slot": str(train_slots.max()),
        "valid": final.valid,
        "test": final.test,
        "reference_baseline": reference,
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
