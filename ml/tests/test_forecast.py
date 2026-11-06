import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from test_walk_forward import DAYS, HOURS, LEVELS, START, make_columns, make_config

from foot_traffic import baseline, forecast, walk_forward
from foot_traffic.data import CALENDAR_COLUMNS, build_features, take

DAY = np.timedelta64(1, "D")
TRAIN_END = np.datetime64("2025-06-02")  # 서비스 모델 학습 데이터의 다음 날(월요일)
ROUNDS = 10
HOURS_PER_DAY = 24


@pytest.fixture
def calendar_path(tmp_path: Path) -> Path:
    """forecast 는 달력 열 전부를 읽는다. 주말을 쉬는 날로 둔다."""
    dates = np.arange(
        START - 30 * DAY, START + (DAYS + 30) * DAY, dtype="datetime64[D]"
    )
    weekend = (((dates.astype(np.int64) + 3) % 7) >= 5).astype(np.float32)
    table = {"date": pa.array(dates, type=pa.date32())}
    for name in CALENDAR_COLUMNS:
        table[name] = weekend if name == "is_off_day" else np.zeros(dates.size)
    path = tmp_path / "daily.parquet"
    pq.write_table(pa.table(table), path)
    return path


def service(calendar_path: Path) -> tuple[dict, object, dict, dict]:
    """TRAIN_END 앞 데이터로 서비스 모델을 학습한다.

    반환: (전체 열, 모델, 메타, 설정)
    """
    columns = make_columns()
    config = make_config()
    history = take(columns, columns["slot_start"] < TRAIN_END)
    booster, meta = walk_forward.fit_service(history, config, calendar_path, ROUNDS)
    return columns, booster, meta, config


def real_day(columns: dict, sensors: list[int], day: np.datetime64) -> dict:
    mask = np.isin(columns["sensor_code"], sensors) & (
        columns["slot_start"].astype("datetime64[D]") == day
    )
    return take(columns, mask)


def row_key(part: dict) -> np.ndarray:
    """(센서, 시각) 정렬 키."""
    return part["sensor_code"].astype(np.int64) * 10**12 + part["slot_start"].astype(
        np.int64
    )


def test_day_of_week_starts_on_monday() -> None:
    assert forecast.day_of_week(np.datetime64("2025-06-02")) == 0
    assert forecast.day_of_week(np.datetime64("2025-06-08")) == 6


def test_fit_service_uses_all_rows_and_records_as_of(calendar_path: Path) -> None:
    _, _, meta, _ = service(calendar_path)
    assert meta["as_of"] == str(TRAIN_END)
    assert np.datetime64(meta["train_last_slot"]) < TRAIN_END
    assert meta["rounds"] == ROUNDS
    assert meta["feature_groups"] == make_config()["walk_forward"]["feature_groups"]


def test_booster_round_trips_through_a_korean_path(
    calendar_path: Path, tmp_path: Path
) -> None:
    columns, booster, _, _ = service(calendar_path)
    path = tmp_path / "공유 드라이브" / "모델.txt"
    walk_forward.save_booster(booster, path)
    loaded = walk_forward.load_booster(path)
    x = np.zeros((3, booster.num_feature()), dtype=np.float32)
    assert np.allclose(loaded.predict(x), booster.predict(x))


def test_median_rounds_uses_official_folds_only(tmp_path: Path) -> None:
    folds = [
        {"rounds": 100, "official": True},
        {"rounds": 300, "official": True},
        {"rounds": 200, "official": True},
        {"rounds": 9000, "official": False},
    ]
    (tmp_path / "folds.json").write_text(json.dumps({"folds": folds}))
    assert walk_forward.median_rounds(tmp_path) == 200
    with pytest.raises(SystemExit):
        walk_forward.median_rounds(tmp_path / "missing")


def test_forecast_gives_24_non_negative_hours_per_sensor(calendar_path: Path) -> None:
    columns, booster, meta, config = service(calendar_path)
    history = take(columns, columns["slot_start"] < TRAIN_END)
    rows, pred = forecast.forecast(
        history, calendar_path, booster, meta, config, [1, 3], str(TRAIN_END + 2 * DAY)
    )
    assert pred.size == 2 * HOURS_PER_DAY
    assert sorted(set(rows["sensor_code"].tolist())) == [1, 3]
    assert (pred >= 0).all() and np.isfinite(pred).all()
    # 큰 센서가 더 많이 예측된다(센서 규모를 따라간다).
    big = rows["sensor_code"] == 3
    assert pred[big].sum() > pred[~big].sum()


def test_future_rows_match_real_rows_of_the_same_day(calendar_path: Path) -> None:
    columns, _, _, _ = service(calendar_path)
    day = TRAIN_END + 2 * DAY
    real = real_day(columns, [2], day)
    fake = forecast.future_rows(columns, calendar_path, [2], day)
    fake = take(fake, np.isin(fake["hour_of_day"], HOURS))
    for name in ("sensor_code", "district", "lon", "day_of_week", "is_off_day"):
        assert fake[name].tolist() == real[name].tolist(), name
    assert fake["slot_start"].tolist() == real["slot_start"].tolist()
    assert np.isnan(fake["foot_traffic"]).all()


def test_forecast_features_equal_the_training_pipeline(calendar_path: Path) -> None:
    """실측이 있는 날을 forecast 로 예측한 값 = walk-forward 경로로 만든 피처의 예측."""
    columns, booster, meta, config = service(calendar_path)
    day = TRAIN_END + 2 * DAY
    sensors = list(LEVELS)
    target = real_day(columns, sensors, day)
    prepared, fallback = forecast.prepare_target(
        columns, target, calendar_path, meta, config
    )
    got, _ = forecast.predict_prepared(booster, meta, config, prepared, fallback)

    # walk-forward 와 같은 방식: 평가 구간까지 prepare 하고 학습 행으로 fallback 을
    # 만든다.
    part, _, _ = walk_forward.prepare(
        columns, TRAIN_END, day + DAY, config, calendar_path
    )
    evaluate = take(part, part["slot_start"].astype("datetime64[D]") == day)
    median = walk_forward.fit_median(take(part, part["slot_start"] < TRAIN_END))
    x, _ = build_features(
        evaluate, meta["vocab"], config["features"], meta["feature_groups"]
    )
    reference = baseline.reference_level(
        evaluate,
        walk_forward.median_fallback(evaluate, median),
        meta["target_transform"],
    )
    expected = walk_forward.predict(booster, x) * reference
    assert np.allclose(
        got[np.argsort(row_key(prepared))], expected[np.argsort(row_key(evaluate))]
    )


def test_forecast_ignores_values_within_gap_days(calendar_path: Path) -> None:
    columns, booster, meta, config = service(calendar_path)
    day = TRAIN_END + 2 * DAY
    gap = meta["recent_level"]["gap_days"]
    base_rows, base_pred = forecast.forecast(
        columns, calendar_path, booster, meta, config, [2], str(day)
    )
    poisoned = {name: values.copy() for name, values in columns.items()}
    recent_days = poisoned["slot_start"].astype("datetime64[D]") > day - gap * DAY
    poisoned["foot_traffic"][recent_days] *= 50
    _, pred = forecast.forecast(
        poisoned, calendar_path, booster, meta, config, [2], str(day)
    )
    assert np.allclose(pred, base_pred)


def test_forecast_refuses_days_without_recent_data(calendar_path: Path) -> None:
    columns, booster, meta, config = service(calendar_path)
    history = take(columns, columns["slot_start"] < TRAIN_END)
    gap = meta["recent_level"]["gap_days"]
    too_far = TRAIN_END - DAY + (gap + 1) * DAY
    with pytest.raises(ValueError, match="학습셋을 갱신"):
        forecast.forecast(
            history, calendar_path, booster, meta, config, [1], str(too_far)
        )


def test_forecast_refuses_unknown_sensor_and_missing_calendar(
    calendar_path: Path,
) -> None:
    columns, booster, meta, config = service(calendar_path)
    day = str(TRAIN_END + DAY)
    with pytest.raises(ValueError, match="센서 99"):
        forecast.forecast(columns, calendar_path, booster, meta, config, [99], day)
    with pytest.raises(ValueError, match="달력에"):
        forecast.forecast(
            columns, calendar_path, booster, meta, config, [1], "2030-01-01"
        )


def test_config_for_model_takes_preprocessing_from_meta(calendar_path: Path) -> None:
    _, _, meta, config = service(calendar_path)
    changed = make_config()
    changed["recent_level"]["gap_days"] = 7
    changed["walk_forward"]["feature_groups"] = ["base"]
    merged = forecast.config_for_model(changed, meta)
    assert (
        walk_forward.recent_config(merged)["gap_days"]
        == meta["recent_level"]["gap_days"]
    )
    assert walk_forward.feature_groups(merged) == meta["feature_groups"]


def test_future_rows_take_weather_per_sensor(calendar_path: Path) -> None:
    columns, _, _, _ = service(calendar_path)
    day = TRAIN_END + 2 * DAY
    temp = np.stack([np.full(HOURS_PER_DAY, 5.0), np.arange(HOURS_PER_DAY) * 1.0])
    rows = forecast.future_rows(columns, calendar_path, [1, 3], day, temp=temp)
    first = rows["sensor_code"] == 1
    assert np.allclose(rows["temp"][first], 5.0)
    assert np.allclose(rows["temp"][~first], np.arange(HOURS_PER_DAY))
    assert np.isnan(rows["rain_mm"]).all()


def test_future_rows_spread_one_day_of_weather_to_all_sensors(
    calendar_path: Path,
) -> None:
    columns, _, _, _ = service(calendar_path)
    day = TRAIN_END + 2 * DAY
    rain = np.arange(HOURS_PER_DAY) * 0.5
    rows = forecast.future_rows(columns, calendar_path, [1, 3], day, rain_mm=rain)
    for sensor in (1, 3):
        own = rows["sensor_code"] == sensor
        assert np.allclose(rows["rain_mm"][own], rain)


def test_future_rows_refuse_wrong_weather_shape(calendar_path: Path) -> None:
    columns, _, _, _ = service(calendar_path)
    day = TRAIN_END + 2 * DAY
    with pytest.raises(ValueError, match="모양"):
        forecast.future_rows(
            columns, calendar_path, [1, 3], day, temp=np.zeros((3, HOURS_PER_DAY))
        )
