"""서비스용 모델로 센서의 하루 시간대별 유동인구를 예측한다(다시 학습하지 않는다).

실행: ml/ 에서 uv run python -m foot_traffic.forecast --sensor 4015 --date 2026-10-27
      [--temp 18 --rain 0]
- 모델: DATA_DIR 의 serve.model_dir(train.py 가 저장한다).
- 입력: 학습셋(센서 이력)과 달력. 예측하려는 날의 recent_level.gap_days 일 전까지의 센서
  데이터가 학습셋에 있어야 한다(서비스는 학습셋이 매일 갱신된다고 가정한다).
- 날씨: 시각별 기온(℃)·강수(mm)를 넘긴다. 주지 않으면 결측으로 두고 예측한다.
- 피처는 학습 때와 같은 함수(walk_forward.prepare)로, 메타에 저장된 설정(단절 보정,
  최근 수준, 피처 그룹)대로 만든다. config.yaml 이 바뀌어도 모델과 어긋나지 않는다.
"""

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pyarrow.parquet as pq

from foot_traffic import baseline
from foot_traffic.common import CONFIG_PATH, data_path, load_config
from foot_traffic.data import (
    CALENDAR_COLUMNS,
    Columns,
    build_features,
    load_columns,
    take,
)
from foot_traffic.recent import HOURS_PER_DAY
from foot_traffic.walk_forward import (
    DAY,
    fit_median,
    load_booster,
    median_fallback,
    predict,
    prepare,
)

# datetime64 의 0 일(1970-01-01)은 목요일이다. 학습셋의 day_of_week 는 월요일이 0 이다.
EPOCH_DAY_OF_WEEK = 3
DAYS_PER_WEEK = 7
# 센서 위치·구 정보처럼 하루 안에서 바뀌지 않는 열. 그 센서의 가장 최근 행에서 가져온다.
SENSOR_COLUMNS = ["sensor_code", "district", "lon", "lat"]


def load_service(config: dict[str, Any]) -> tuple[lgb.Booster, dict[str, Any]]:
    """공유 폴더의 서비스용 모델과 메타."""
    serve = config["serve"]
    model_dir = data_path(serve["model_dir"])
    meta_path = model_dir / serve["meta_file"]
    if not meta_path.exists():
        raise SystemExit(
            f"공유 폴더에 서비스 모델이 없습니다({serve['model_dir']}). "
            "DATA_DIR 설정을 확인하거나 python -m foot_traffic.train 으로 만드세요."
        )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return load_booster(model_dir / serve["model_file"]), meta


def config_for_model(config: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """config 위에 메타의 전처리·피처 설정을 덮어쓴다. 학습 때와 같은 피처를 만든다."""
    merged = copy.deepcopy(config)
    merged["recent_level"] = meta["recent_level"]
    merged["target"] = meta["target_transform"]
    merged["features"] = {
        **merged["features"],
        "temp_bin_c": meta["temp_bin_c"],
        "rain_bins_mm": meta["rain_bins_mm"],
    }
    merged["walk_forward"] = {
        **merged["walk_forward"],
        **meta["walk_forward"],
        "recent_level": {},
        "feature_groups": meta["feature_groups"],
    }
    return merged


def meta_as_of(meta: dict[str, Any]) -> np.datetime64:
    """학습 종료일. 단절 판단·보정 계수·기준값 fallback 을 이 날 앞 데이터로 만든다."""
    if "as_of" in meta:
        return np.datetime64(meta["as_of"], "D")
    last = np.datetime64(meta["train_last_slot"]).astype("datetime64[D]")
    return last + DAY


def day_of_week(day: np.datetime64) -> int:
    """월요일 0 ~ 일요일 6."""
    return int((day.astype(np.int64) + EPOCH_DAY_OF_WEEK) % DAYS_PER_WEEK)


def calendar_row(calendar_path: Path, day: np.datetime64) -> dict[str, float]:
    """달력(12 단계)에서 그날의 달력 열."""
    table = pq.read_table(calendar_path, columns=["date", *CALENDAR_COLUMNS])
    dates = table["date"].to_numpy().astype("datetime64[D]")
    found = np.flatnonzero(dates == day)
    if found.size == 0:
        raise ValueError(
            f"달력에 {day} 가 없습니다(있는 기간 {dates.min()} ~ {dates.max()}). "
            "pipeline 12 단계 달력 기간을 늘리세요."
        )
    row = int(found[0])
    return {name: float(table[name][row].as_py()) for name in CALENDAR_COLUMNS}


def sensor_weather(
    values: np.ndarray | None, sensor_count: int, name: str
) -> np.ndarray:
    """날씨 값을 (센서 수, 24) 로 맞춘다. None 이면 모두 NaN."""
    if values is None:
        return np.full((sensor_count, HOURS_PER_DAY), np.nan)
    array = np.asarray(values, dtype=np.float64)
    if array.shape == (HOURS_PER_DAY,):
        return np.tile(array, (sensor_count, 1))
    if array.shape == (sensor_count, HOURS_PER_DAY):
        return array
    raise ValueError(
        f"{name} 은 ({HOURS_PER_DAY},) 또는 (센서 수 {sensor_count}, {HOURS_PER_DAY}) "
        f"모양이어야 합니다(받은 모양 {array.shape})."
    )


def future_rows(
    columns: Columns,
    calendar_path: Path,
    sensors: list[int],
    day: np.datetime64,
    temp: np.ndarray | None = None,
    rain_mm: np.ndarray | None = None,
) -> Columns:
    """실측이 없는 날의 센서별 24시간 행(foot_traffic 은 NaN).

    temp·rain_mm 은 시각별(24개) 값이다. 모양이 (24,) 이면 모든 센서에 같게, (센서 수,
    24) 이면 sensors 순서대로 센서마다 넣는다. 없으면 NaN 이다. h 번째 값은 h 시에
    시작하는 한 시간 행에 붙는다. 학습셋(13 단계)은 이 행에 h+1 시 정시 날씨를 붙였다.
    """
    calendar = calendar_row(calendar_path, day)
    hours = np.arange(HOURS_PER_DAY)
    weather = {
        "temp": sensor_weather(temp, len(sensors), "temp"),
        "rain_mm": sensor_weather(rain_mm, len(sensors), "rain_mm"),
    }
    parts: list[Columns] = []
    for index, sensor in enumerate(sensors):
        own = np.flatnonzero(columns["sensor_code"] == sensor)
        if own.size == 0:
            raise ValueError(f"학습셋에 센서 {sensor} 가 없습니다.")
        latest = own[np.argmax(columns["slot_start"][own])]
        rows: Columns = {
            name: np.full(
                HOURS_PER_DAY, columns[name][latest], dtype=columns[name].dtype
            )
            for name in SENSOR_COLUMNS
        }
        slot_dtype = columns["slot_start"].dtype
        rows["slot_start"] = (
            day.astype(slot_dtype) + hours.astype("timedelta64[h]")
        ).astype(slot_dtype)
        rows["day_of_week"] = np.full(
            HOURS_PER_DAY, day_of_week(day), dtype=columns["day_of_week"].dtype
        )
        rows["hour_of_day"] = hours.astype(columns["hour_of_day"].dtype)
        for name in ("temp", "rain_mm"):
            rows[name] = weather[name][index].astype(columns[name].dtype)
        for name, value in calendar.items():
            rows[name] = np.full(HOURS_PER_DAY, value, dtype=columns[name].dtype)
        rows["foot_traffic"] = np.full(
            HOURS_PER_DAY, np.nan, dtype=columns["foot_traffic"].dtype
        )
        parts.append({name: rows[name] for name in columns})
    return {name: np.concatenate([p[name] for p in parts]) for name in columns}


def prepare_target(
    columns: Columns,
    target: Columns,
    calendar_path: Path,
    meta: dict[str, Any],
    config: dict[str, Any],
) -> tuple[Columns, np.ndarray]:
    """예측할 하루의 행(target)에 학습 때와 같은 전처리·피처를 붙인다.

    이력은 그날 앞 행만 쓴다. 반환: (피처를 붙인 target 행, 기준값 fallback)
    """
    cfg = config_for_model(config, meta)
    day = target["slot_start"].min().astype("datetime64[D]")
    if np.any(target["slot_start"].astype("datetime64[D]") != day):
        raise ValueError("target 은 하루치 행이어야 합니다.")
    known = set(meta["vocab"]["sensor_code"])
    unknown = sorted(set(target["sensor_code"].tolist()) - known)
    if unknown:
        raise ValueError(f"모델이 학습하지 않은 센서입니다: {unknown}")
    gap = cfg["recent_level"]["gap_days"]
    last_day = columns["slot_start"].max().astype("datetime64[D]")
    if day - gap * DAY > last_day:
        raise ValueError(
            f"{day} 를 예측하려면 {day - gap * DAY} 까지의 센서 데이터가 필요합니다"
            f"(학습셋 마지막 날 {last_day}). 학습셋을 갱신하세요."
        )
    history = take(columns, columns["slot_start"] < day)
    combined = {name: np.concatenate([history[name], target[name]]) for name in columns}
    as_of = meta_as_of(meta)
    part, _, _ = prepare(combined, as_of, day + DAY, cfg, calendar_path)
    median = fit_median(take(part, part["slot_start"] < as_of))
    prepared = take(part, part["slot_start"] >= day)
    return prepared, median_fallback(prepared, median)


def predict_prepared(
    booster: lgb.Booster,
    meta: dict[str, Any],
    config: dict[str, Any],
    prepared: Columns,
    fallback: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """(모델 예측, 최근 수준 baseline)(명/시간)."""
    cfg = config_for_model(config, meta)
    matrix, names = build_features(
        prepared, meta["vocab"], cfg["features"], meta["feature_groups"]
    )
    if names != meta["feature_names"]:
        raise ValueError("모델의 피처 목록과 설정이 다릅니다. 모델을 다시 만드세요.")
    reference = baseline.reference_level(prepared, fallback, meta["target_transform"])
    model = predict(booster, matrix) * reference
    return model, baseline.recent_predict(prepared, fallback)


def forecast(
    columns: Columns,
    calendar_path: Path,
    booster: lgb.Booster,
    meta: dict[str, Any],
    config: dict[str, Any],
    sensors: list[int],
    day: str,
    temp: np.ndarray | None = None,
    rain_mm: np.ndarray | None = None,
) -> tuple[Columns, np.ndarray]:
    """센서들의 그날 24시간 예측.

    반환: (피처를 붙인 행: sensor_code·hour_of_day 등, 예측 명/시간)
    """
    target = future_rows(
        columns, calendar_path, sensors, np.datetime64(day, "D"), temp, rain_mm
    )
    prepared, fallback = prepare_target(columns, target, calendar_path, meta, config)
    model, _ = predict_prepared(booster, meta, config, prepared, fallback)
    return prepared, model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--sensor", type=int, required=True, help="센서 코드")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--temp", type=float, help="그날 모든 시간의 기온(℃)")
    parser.add_argument("--rain", type=float, help="그날 모든 시간의 강수(mm)")
    args = parser.parse_args()
    config = load_config(args.config)
    booster, meta = load_service(config)
    columns = load_columns(data_path(config["walk_forward"]["training_set"]))
    temp = None if args.temp is None else np.full(HOURS_PER_DAY, args.temp)
    rain = None if args.rain is None else np.full(HOURS_PER_DAY, args.rain)
    try:
        rows, model = forecast(
            columns,
            data_path(config["data"]["calendar"]),
            booster,
            meta,
            config,
            [args.sensor],
            args.date,
            temp,
            rain,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(
        f"센서 {args.sensor} · {args.date} 예측 (모델 학습 ~{meta['train_last_slot']})"
    )
    print(f"{'시각':>4} {'예측':>7}")
    for hour, value in zip(rows["hour_of_day"], model):
        print(f"{int(hour):>3}시 {value:>7.0f}")
    print(f"하루 합계 {model.sum():,.0f}명")


if __name__ == "__main__":
    main()
