"""walk-forward 검증과 최종 테스트.

실행: ml/ 에서 uv run python -m foot_traffic.walk_forward [--skip-final | --final-only]
- fold 마다 검증 시작일 gap_days 일 전까지의 행으로만 학습하고 그 주를 평가한다. 학습
  종료일 이후(평가 직전 gap_days 일 포함)는 학습에 쓰지 않는다. 무작위 분할은 없다.
- 센서 단절은 학습 종료일(as_of) 이전 데이터만으로 판단한다(level_break.py).
- 범주 목록, 기준값의 fallback 통계, baseline 은 모두 학습 구간 행으로만 만든다.
- 모델·하이퍼파라미터·타깃(비율, 기준값 가중)은 기존과 같다. 목적함수는 L1 로 고정한다.
- 반복 수는 fold 학습 구간의 마지막 early_stopping_days 일을 내부 검증으로 정하고
  (검증 주는 쓰지 않는다), 그 반복 수로 학습 구간 전체를 다시 학습해 검증 주를 평가한다.
  정하는 방식은 early_stopping.method 다. smoothed 는 고정 횟수 학습의 검증 곡선을
  이동평균으로 매끄럽게 한 바닥을, patience 는 lightgbm 조기 종료(검증이 N번 나아지지
  않으면 멈춤)를 쓴다.
- 최종 단계(--skip-final 이 아니면): fold 반복 수의 중앙값으로 최종 테스트 시작 gap_days
  일 전까지의 모든 행을 학습해 최종 테스트를 한 번만 평가한다. fold 단계는 마지막 fold
  검증 이후의 행(최종 테스트 포함)을 읽지 않는다.
- 출력(output_dir): folds.json, folds_summary.json, final_test.json, 최종 모델과 메타.
- 실험 항목(피처 gap, 단절 과도기·보정, 고장 의심일, 추가 피처, 방학, 하이퍼파라미터)은
  config.yaml 의 walk_forward 절에서 켠다.
- 서비스용 모델(전체 데이터로 학습)은 train.py 가 이 모듈의 fit_service 로 만든다.
"""

import argparse
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

from foot_traffic import baseline, level_break, metrics, recent
from foot_traffic.common import CONFIG_PATH, data_path, load_config, repo_path
from foot_traffic.data import (
    Columns,
    add_off_adjacent,
    add_recent_levels,
    add_vacation,
    build_features,
    load_columns,
    make_vocab,
    take,
)

DAY = np.timedelta64(1, "D")
ROUND_DIGITS = 4
# 메타에 남기는 walk_forward 설정. 예측(forecast)이 학습 때와 같은 전처리에 쓴다.
META_WALK_FORWARD_KEYS = (
    "gap_days",
    "folds",
    "extra_folds",
    "valid_days",
    "vacation_months",
    "outage",
    "level_break",
)


def window_bounds(
    eval_start: str, eval_end_exclusive: np.datetime64, gap_days: int
) -> tuple[np.datetime64, np.datetime64, np.datetime64]:
    """(학습 종료일, 평가 시작, 평가 끝). 학습은 종료일 앞 행, 평가는 [시작, 끝)."""
    start = np.datetime64(eval_start, "D")
    return start - gap_days * DAY, start, eval_end_exclusive


def recent_config(config: dict[str, Any]) -> dict[str, Any]:
    """최근 수준 설정: recent_level 절 위에 walk_forward.recent_level 을 덮어쓴다."""
    return {**config["recent_level"], **config["walk_forward"].get("recent_level", {})}


def feature_groups(config: dict[str, Any]) -> list[str]:
    """쓸 피처 그룹(features.groups 의 이름)."""
    return config["walk_forward"]["feature_groups"]


def model_config(config: dict[str, Any]) -> dict[str, Any]:
    """model 절의 params 위에 walk_forward.model_params 를 덮어쓴다(튜닝 실험)."""
    model = config["model"]
    overrides = config["walk_forward"].get("model_params", {})
    return {**model, "params": {**model["params"], **overrides}}


def prepare(
    columns: Columns,
    as_of: np.datetime64,
    eval_end: np.datetime64,
    config: dict[str, Any],
    calendar_path: Path,
) -> tuple[Columns, list[int], dict[str, Any]]:
    """eval_end 앞 행만 남기고, as_of 시점 단절 센서 행을 정리하고, 피처를 더한다.

    eval_end 이후 행은 읽지 않는다. 최근 수준 피처는 각 행의 gap 일 이전 데이터만 쓰므로
    평가 행의 피처는 그 행보다 gap 일 앞선 데이터에서만 만들어진다.
    반환: (열, 단절 센서, 정리 통계)
    """
    part = take(columns, columns["slot_start"] < eval_end)
    wf = config["walk_forward"]
    flagged = level_break.flagged_sensors(part, wf["level_break"], as_of)
    keep, scale, stats = level_break.clean_break(
        part, flagged, wf["level_break"], as_of
    )
    if scale is not None:  # 단절 전 행을 이후 수준에 맞춘다(학습 구간 행만 해당).
        part["foot_traffic"] = (part["foot_traffic"] * scale).astype(np.float32)
    part = take(part, keep)
    add_off_adjacent(part, calendar_path)
    if wf.get("vacation_months"):
        add_vacation(part, wf["vacation_months"])
    exclude = recent.outage_rows(part, wf["outage"]) if wf.get("outage") else None
    stats["rows_outage_excluded_from_levels"] = (
        0 if exclude is None else int(exclude.sum())
    )
    add_recent_levels(part, recent_config(config), exclude)
    return part, flagged, stats


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
    """0 이상으로 자른 모델 출력. L1·L2 는 음수가 나올 수 있다."""
    return np.clip(
        booster.predict(matrix, num_iteration=booster.best_iteration), 0.0, None
    )


def fit_fixed(
    objective: str,
    train: tuple[np.ndarray, np.ndarray, np.ndarray | None],
    names: list[str],
    categorical: list[str],
    model_config: dict[str, Any],
    rounds: int,
) -> lgb.Booster:
    """조기 종료 없이 rounds 번 학습한다(기존 train_model 과 같은 파라미터)."""
    params = {
        **model_config["params"],
        "objective": objective,
        "metric": "l1",
        "seed": model_config["seed"],
    }
    dataset = lgb.Dataset(
        train[0],
        train[1],
        weight=train[2],
        feature_name=names,
        categorical_feature=[n for n in categorical if n in names],
    )
    return lgb.train(params, dataset, num_boost_round=rounds)


def pick(weights: np.ndarray | None, mask: np.ndarray) -> np.ndarray | None:
    return None if weights is None else weights[mask]


def smoothed_best_iteration(curve: list[float], window: int) -> int:
    """검증 곡선(반복마다 가중 MAE)을 window 회 이동평균으로 매끄럽게 한 최솟값 반복 수.

    한두 번의 출렁임이 아니라 곡선의 전반적인 바닥을 고른다. 반복 수는 1부터 센다.
    """
    values = np.asarray(curve, dtype=np.float64)
    if values.size <= window:
        return int(np.argmin(values)) + 1
    smooth = np.convolve(values, np.ones(window) / window, mode="valid")
    return int(np.argmin(smooth)) + window // 2 + 1


def validation_curve(
    objective: str,
    fit: tuple[np.ndarray, np.ndarray, np.ndarray | None],
    valid: tuple[np.ndarray, np.ndarray, np.ndarray | None],
    names: list[str],
    categorical: list[str],
    model_config: dict[str, Any],
    rounds: int,
) -> list[float]:
    """조기 종료 없이 rounds 번 학습하며 검증 가중 MAE(l1)를 반복마다 기록한다."""
    params = {
        **model_config["params"],
        "objective": objective,
        "metric": "l1",
        "seed": model_config["seed"],
    }
    train_set = lgb.Dataset(
        fit[0],
        fit[1],
        weight=fit[2],
        feature_name=names,
        categorical_feature=[n for n in categorical if n in names],
    )
    valid_set = lgb.Dataset(valid[0], valid[1], weight=valid[2], reference=train_set)
    record: dict[str, dict[str, list[float]]] = {}
    lgb.train(
        params,
        train_set,
        num_boost_round=rounds,
        valid_sets=[valid_set],
        callbacks=[lgb.record_evaluation(record)],
    )
    return record["valid_0"]["l1"]


def training_data(
    part: Columns, as_of: np.datetime64, config: dict[str, Any]
) -> dict[str, Any]:
    """prepare 를 거친 열에서 as_of 앞 행으로 학습 행렬·비율 라벨·가중치를 만든다.

    범주 목록과 기준값 fallback(센서·요일·시각 중앙값)은 학습 행으로만 만든다. 최근
    수준이 없는 학습 행은 비율을 못 만들어 뺀다.
    """
    target = config["target"]
    train = take(part, part["slot_start"] < as_of)
    rows_raw = int(train["foot_traffic"].size)
    vocab = make_vocab(train, config["features"]["categorical"])
    median = fit_median(train)
    ref = baseline.reference_level(train, np.full(rows_raw, np.nan), target)
    usable = ~np.isnan(ref)
    train, ref = take(train, usable), ref[usable]
    x, names = build_features(train, vocab, config["features"], feature_groups(config))
    weight = ref ** target["weight_power"] if target["weight"] == "ref" else None
    return {
        "train": train,
        "x": x,
        "label": train["foot_traffic"] / ref,
        "weight": weight,
        "names": names,
        "vocab": vocab,
        "median": median,
        "rows_raw": rows_raw,
        "rows_without_recent_level": int((~usable).sum()),
    }


def fit_median(train: Columns) -> tuple[dict[int, float], dict[int, float]]:
    """학습 행의 센서·요일·시각 중앙값(없으면 센서 중앙값). 기준값 fallback 이다."""
    return baseline.fit_baseline(
        baseline.slot_keys(
            train["sensor_code"], train["day_of_week"], train["hour_of_day"]
        ),
        train["sensor_code"],
        train["foot_traffic"],
        "median",
    )


def median_fallback(
    part: Columns, median: tuple[dict[int, float], dict[int, float]]
) -> np.ndarray:
    """학습 행의 센서·요일·시각 중앙값(training_data 의 median)으로 만든 fallback."""
    by_slot, by_sensor = median
    return baseline.predict_baseline(
        baseline.slot_keys(
            part["sensor_code"], part["day_of_week"], part["hour_of_day"]
        ),
        part["sensor_code"],
        by_slot,
        by_sensor,
    )


def run_window(
    columns: Columns,
    as_of: np.datetime64,
    eval_start: np.datetime64,
    eval_end: np.datetime64,
    config: dict[str, Any],
    calendar_path: Path,
    rounds: int | None = None,
) -> dict[str, Any]:
    """as_of 앞 행으로 학습하고 [eval_start, eval_end) 를 평가한다.

    rounds 가 없으면 학습 구간 마지막 early_stopping_days 일로 조기 종료해 반복 수를
    정하고 학습 구간 전체로 다시 학습한다. 있으면 그 반복 수로 한 번만 학습한다.
    """
    wf = config["walk_forward"]
    categorical = config["features"]["categorical"]
    model = model_config(config)
    part, flagged, stats = prepare(columns, as_of, eval_end, config, calendar_path)
    slot = part["slot_start"]
    data = training_data(part, as_of, config)
    train, vocab, names = data["train"], data["vocab"], data["names"]
    x_train, label, weight = data["x"], data["label"], data["weight"]
    evaluate = take(part, (slot >= eval_start) & (slot < eval_end))
    median_eval = median_fallback(evaluate, data["median"])
    ref_eval = baseline.reference_level(evaluate, median_eval, config["target"])
    x_eval, _ = build_features(
        evaluate, vocab, config["features"], feature_groups(config)
    )

    best_iteration = None
    tick = time.time()
    print(
        f"  학습 준비 끝: 학습 {train['foot_traffic'].size:,}행, 평가 "
        f"{evaluate['foot_traffic'].size:,}행",
        flush=True,
    )
    stopping: dict[str, Any] | None = None
    if rounds is None:
        fit = train["slot_start"] < as_of - wf["early_stopping_days"] * DAY
        es = ~fit
        fit_part = (x_train[fit], label[fit], pick(weight, fit))
        es_part = (x_train[es], label[es], pick(weight, es))
        options = wf.get("early_stopping", {"method": "patience"})
        if options["method"] == "smoothed":
            # 고정 횟수 학습하며 검증 곡선을 기록하고, 이동평균으로 매끄럽게 한 바닥을
            # 고른다.
            curve = validation_curve(
                wf["objective"],
                fit_part,
                es_part,
                names,
                categorical,
                model,
                options["max_rounds"],
            )
            best_iteration = smoothed_best_iteration(curve, options["smooth_window"])
            stopping = {
                "method": "smoothed",
                "max_rounds": options["max_rounds"],
                "smooth_window": options["smooth_window"],
                "raw_argmin_iteration": int(np.argmin(curve)) + 1,
                "curve_every_10_rounds": [round(v, 5) for v in curve[9::10]],
            }
        else:  # patience: 검증이 early_stopping_rounds 번 나아지지 않으면 멈춘다.
            stopper = train_model(
                wf["objective"],
                fit_part,
                es_part,
                names,
                categorical,
                model,
            )
            best_iteration = int(stopper.best_iteration or model["num_boost_round"])
            stopping = {"method": "patience"}
        stopping["inner_validation_days"] = wf["early_stopping_days"]
        stopping["inner_validation_rows"] = int(es.sum())
        rounds = best_iteration
        print(
            f"  조기 종료 반복 {best_iteration}회 ({stopping['method']}, "
            f"{time.time() - tick:.0f}s)",
            flush=True,
        )
    booster = fit_fixed(
        wf["objective"],
        (x_train, label, weight),
        names,
        categorical,
        model,
        rounds,
    )
    pred = predict(booster, x_eval) * ref_eval
    base = baseline.recent_predict(evaluate, median_eval)
    y = evaluate["foot_traffic"]
    return {
        "booster": booster,
        "names": names,
        "vocab": vocab,
        "train": train,
        "evaluate": evaluate,
        "pred": pred,
        "base": base,
        "median_eval": median_eval,
        "info": {
            "train_end": str(as_of),
            "eval_start": str(eval_start),
            "eval_end_exclusive": str(eval_end),
            "train_first_slot": str(train["slot_start"].min()),
            "train_last_slot": str(train["slot_start"].max()),
            "eval_first_slot": str(evaluate["slot_start"].min()),
            "eval_last_slot": str(evaluate["slot_start"].max()),
            "rows_dropped_level_break": stats["rows_dropped"],
            "level_break_sensors": len(flagged),
            "level_break_cleanup": stats,
            "train_rows_before_level_drop": data["rows_raw"],
            "train_rows": int(train["foot_traffic"].size),
            "train_rows_without_recent_level": data["rows_without_recent_level"],
            "train_sensors": len(np.unique(train["sensor_code"])),
            "eval_rows": int(y.size),
            "eval_sensors": len(np.unique(evaluate["sensor_code"])),
            "eval_sensors_not_in_train": int(
                len(set(evaluate["sensor_code"].tolist()) - set(vocab["sensor_code"]))
            ),
            "rounds": rounds,
            "early_stopping_best_iteration": best_iteration,
            "early_stopping": stopping,
        },
    }


def window_metrics(y: np.ndarray, pred: np.ndarray, base: np.ndarray) -> dict[str, Any]:
    """MAE, RMSE, WAPE(오차 합 / 실제 합)와 baseline 대비 개선율."""

    def scores(p: np.ndarray) -> dict[str, float]:
        return {
            "mae": round(metrics.mae(y, p), ROUND_DIGITS),
            "rmse": round(metrics.rmse(y, p), ROUND_DIGITS),
            "wape": round(metrics.error_rate(y, p), ROUND_DIGITS),
        }

    model, reference = scores(pred), scores(base)
    return {
        "model": model,
        "baseline": reference,
        "improvement": {
            key: metrics.improvement(reference[key], model[key]) for key in model
        },
    }


def by_sensor(
    sensor_code: np.ndarray, y: np.ndarray, pred: np.ndarray, base: np.ndarray
) -> dict[str, dict[str, float]]:
    """센서별 행 수, 실제 평균, 모델·baseline MAE."""
    result = {}
    for code in np.unique(sensor_code):
        m = sensor_code == code
        result[str(int(code))] = {
            "rows": int(m.sum()),
            "mean_actual": round(float(y[m].mean()), 2),
            "model_mae": round(metrics.mae(y[m], pred[m]), ROUND_DIGITS),
            "baseline_mae": round(metrics.mae(y[m], base[m]), ROUND_DIGITS),
        }
    return result


def summarize_folds(folds: list[dict[str, Any]]) -> dict[str, Any]:
    """fold 간 평균·표준편차(표본)·최솟값·최댓값과 최악 fold, 센서별 fold 간 편차."""
    summary: dict[str, Any] = {}
    for group in ("model", "baseline", "improvement"):
        summary[group] = {}
        for key in ("mae", "rmse", "wape"):
            values = np.array([f["metrics"][group][key] for f in folds])
            summary[group][key] = {
                "mean": round(float(values.mean()), ROUND_DIGITS),
                "std": round(float(values.std(ddof=1)), ROUND_DIGITS)
                if values.size > 1
                else 0.0,
                "min": round(float(values.min()), ROUND_DIGITS),
                "max": round(float(values.max()), ROUND_DIGITS),
            }
    worst = max(folds, key=lambda f: f["metrics"]["model"]["mae"])
    summary["worst_fold_by_model_mae"] = worst["eval_start"]
    summary["folds_model_beats_baseline"] = int(
        sum(f["metrics"]["improvement"]["mae"] > 0 for f in folds)
    )
    sensors: dict[str, list[tuple[float, float]]] = {}
    for fold in folds:
        for code, row in fold["by_sensor"].items():
            sensors.setdefault(code, []).append((row["model_mae"], row["baseline_mae"]))
    summary["by_sensor"] = {
        code: {
            "folds": len(rows),
            "model_mae_mean": round(float(np.mean([r[0] for r in rows])), 2),
            "model_mae_std": round(float(np.std([r[0] for r in rows], ddof=1)), 2)
            if len(rows) > 1
            else 0.0,
            "baseline_mae_mean": round(float(np.mean([r[1] for r in rows])), 2),
        }
        for code, rows in sorted(sensors.items(), key=lambda kv: int(kv[0]))
    }
    return summary


def model_meta(
    config: dict[str, Any],
    names: list[str],
    vocab: dict[str, list[Any]],
    rounds: int,
    as_of: np.datetime64,
    train: Columns,
) -> dict[str, Any]:
    """모델 메타. 예측(forecast)은 이 값만으로 학습 때와 같은 피처를 다시 만든다."""
    wf = config["walk_forward"]
    return {
        "created": date.today().isoformat(),
        "lightgbm": lgb.__version__,
        "objective": wf["objective"],
        "rounds": rounds,
        "feature_names": names,
        "categorical_features": config["features"]["categorical"],
        "vocab": vocab,
        "temp_bin_c": config["features"]["temp_bin_c"],
        "rain_bins_mm": config["features"]["rain_bins_mm"],
        "recent_level": recent_config(config),
        "feature_groups": feature_groups(config),
        "model_params": model_config(config)["params"],
        "target_transform": config["target"],
        "walk_forward": {key: wf.get(key) for key in META_WALK_FORWARD_KEYS},
        # 단절 판단·보정 계수와 기준값 fallback 은 as_of 앞 데이터로 만든다.
        "as_of": str(as_of),
        "train_first_slot": str(train["slot_start"].min()),
        "train_last_slot": str(train["slot_start"].max()),
        "target": "foot_traffic",
        "unit": "명/시간",
    }


def median_rounds(out: Path) -> int:
    """저장된 fold 결과(folds.json)에서 기본 fold 반복 수의 중앙값."""
    path = out / "folds.json"
    if not path.exists():
        raise SystemExit(f"{path} 가 없습니다. 먼저 walk_forward 를 실행하세요.")
    folds = json.loads(path.read_text(encoding="utf-8"))["folds"]
    rounds = [f["rounds"] for f in folds if f.get("official", True)]
    return int(round(float(np.median(rounds))))


def fit_service(
    columns: Columns, config: dict[str, Any], calendar_path: Path, rounds: int
) -> tuple[lgb.Booster, dict[str, Any]]:
    """가진 데이터 전체로 서비스용 모델을 학습한다(평가 구간 없음).

    as_of 는 데이터 마지막 날의 다음 날이다. 전처리·피처·하이퍼파라미터는 fold·최종
    테스트와 같고 반복 수만 rounds 로 고정한다.
    """
    last_slot = columns["slot_start"].max()
    as_of = last_slot.astype("datetime64[D]") + DAY
    part, flagged, stats = prepare(columns, as_of, as_of, config, calendar_path)
    data = training_data(part, as_of, config)
    booster = fit_fixed(
        config["walk_forward"]["objective"],
        (data["x"], data["label"], data["weight"]),
        data["names"],
        config["features"]["categorical"],
        model_config(config),
        rounds,
    )
    meta = model_meta(
        config, data["names"], data["vocab"], rounds, as_of, data["train"]
    )
    meta["train_rows"] = int(data["train"]["foot_traffic"].size)
    meta["level_break_sensors"] = len(flagged)
    meta["level_break_cleanup"] = stats
    return booster, meta


def save_booster(booster: lgb.Booster, path: Path) -> None:
    """모델을 텍스트로 저장한다. lightgbm 의 파일 저장은 Windows 에서 한글 경로(공유
    폴더 등)에 쓰지 못해 문자열로 받아 파이썬으로 쓴다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(booster.model_to_string(), encoding="utf-8")


def load_booster(path: Path) -> lgb.Booster:
    """save_booster 로 저장한 모델(한글 경로도 읽는다)."""
    return lgb.Booster(model_str=path.read_text(encoding="utf-8"))


def write_json(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(content, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def run_folds(
    columns: Columns,
    config: dict[str, Any],
    calendar_path: Path,
    out: Path,
    started: float,
) -> list[dict[str, Any]]:
    """fold 마다 학습·평가하고 folds.json, folds_summary.json 을 저장한다."""
    wf = config["walk_forward"]
    # 보조 fold(extra_folds)는 판단을 돕는 추가 검증 주다. 요약은 기본 fold 만으로 내고
    # 보조 fold 를 더한 요약은 따로 남긴다. 최종 반복 수는 기본 fold 로만 정한다.
    starts = list(wf["folds"]) + list(wf.get("extra_folds", []))
    # fold 단계는 마지막 fold 검증 이후의 행(최종 테스트 포함)을 아예 읽지 않는다.
    last_end = max(
        np.datetime64(start, "D") + wf["valid_days"] * DAY for start in starts
    )
    if last_end > np.datetime64(wf["test_start"], "D") - wf["gap_days"] * DAY:
        raise ValueError("fold 검증 구간이 최종 테스트 앞 gap 과 겹칩니다.")
    fold_columns = take(columns, columns["slot_start"] < last_end)
    print(
        f"fold 단계 입력 {fold_columns['foot_traffic'].size:,}행(< {last_end})",
        flush=True,
    )

    folds = []
    for start in sorted(starts):
        eval_end = np.datetime64(start, "D") + wf["valid_days"] * DAY
        as_of, eval_start, eval_end = window_bounds(start, eval_end, wf["gap_days"])
        result = run_window(
            fold_columns, as_of, eval_start, eval_end, config, calendar_path
        )
        evaluate = result["evaluate"]
        fold = {
            "eval_start": start,
            "official": start in wf["folds"],
            **result["info"],
            "metrics": window_metrics(
                evaluate["foot_traffic"], result["pred"], result["base"]
            ),
            "by_sensor": by_sensor(
                evaluate["sensor_code"],
                evaluate["foot_traffic"],
                result["pred"],
                result["base"],
            ),
        }
        folds.append(fold)
        m = fold["metrics"]
        print(
            f"fold {start}: 학습 {fold['train_rows']:,}행 "
            f"(단절 센서 {fold['level_break_sensors']}개) "
            f"검증 {fold['eval_rows']:,}행/{fold['eval_sensors']}센서 | "
            f"모델 MAE {m['model']['mae']} baseline {m['baseline']['mae']} "
            f"개선 {m['improvement']['mae']:+.1%} 반복 {fold['rounds']} "
            f"({time.time() - started:.0f}s)",
            flush=True,
        )
    write_json(out / "folds.json", {"folds": folds})
    official = [f for f in folds if f["official"]]
    summary = summarize_folds(official)
    if len(official) < len(folds):
        summary["with_extra_folds"] = summarize_folds(folds)
    write_json(out / "folds_summary.json", summary)
    for label, part in (
        ("기본", summary),
        ("보조 포함", summary.get("with_extra_folds")),
    ):
        if part is None:
            continue
        model_mae, base_mae = part["model"]["mae"], part["baseline"]["mae"]
        print(
            f"fold 평균({label}) 모델 MAE {model_mae['mean']} (±{model_mae['std']}) "
            f"baseline {base_mae['mean']} "
            f"개선 {part['improvement']['mae']['mean']:+.1%}, "
            f"최악 fold {part['worst_fold_by_model_mae']}",
            flush=True,
        )
    return official


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument(
        "--skip-final",
        action="store_true",
        help="fold 검증만 하고 최종 테스트는 읽지 않는다",
    )
    parser.add_argument(
        "--output-dir",
        help="결과를 저장할 저장소 기준 폴더(기본: 설정의 walk_forward.output_dir)",
    )
    parser.add_argument(
        "--final-only",
        action="store_true",
        help="저장된 fold 결과(folds.json)의 반복 수로 최종 단계만 실행한다",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    wf = config["walk_forward"]
    calendar_path = data_path(config["data"]["calendar"])
    out = repo_path(args.output_dir or wf["output_dir"])
    started = time.time()

    columns = load_columns(data_path(wf["training_set"]))
    print(f"전체 행 {columns['foot_traffic'].size:,}", flush=True)

    if args.final_only:
        # fold 를 다시 돌리지 않고 저장된 fold 결과의 반복 수를 쓴다.
        print("저장된 fold 결과의 반복 수를 사용한다", flush=True)
    else:
        run_folds(columns, config, calendar_path, out, started)
        if args.skip_final:
            print(f"fold 결과만 저장 → {out}", flush=True)
            return

    rounds = median_rounds(out)
    test_end = np.datetime64(wf["test_end"], "D") + DAY
    as_of, eval_start, eval_end = window_bounds(
        wf["test_start"], test_end, wf["gap_days"]
    )
    result = run_window(
        columns, as_of, eval_start, eval_end, config, calendar_path, rounds=rounds
    )
    evaluate = result["evaluate"]
    y = evaluate["foot_traffic"]
    final = {
        "final_rounds_median_of_folds": rounds,
        **result["info"],
        "metrics": window_metrics(y, result["pred"], result["base"]),
        "by_sensor": by_sensor(
            evaluate["sensor_code"], y, result["pred"], result["base"]
        ),
    }
    write_json(out / "final_test.json", final)
    serve = config["serve"]
    save_booster(result["booster"], out / serve["model_file"])
    meta = model_meta(
        config, result["names"], result["vocab"], rounds, as_of, result["train"]
    )
    meta["test"] = final["metrics"]
    write_json(out / serve["meta_file"], meta)
    m = final["metrics"]
    print(
        f"최종 테스트 {wf['test_start']}~{wf['test_end']}: "
        f"학습 {final['train_rows']:,}행 "
        f"테스트 {final['eval_rows']:,}행 | 모델 MAE {m['model']['mae']} "
        f"baseline {m['baseline']['mae']} 개선 {m['improvement']['mae']:+.1%} → {out} "
        f"({time.time() - started:.0f}s)",
        flush=True,
    )


if __name__ == "__main__":
    main()
