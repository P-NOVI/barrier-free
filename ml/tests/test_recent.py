import numpy as np
import pytest

from foot_traffic import recent

CONFIG = {
    "gap_days": 7,
    "same_hour_days": 28,
    "same_dow_weeks": 8,
    "min_samples_hour": 5,
    "min_samples_dow": 2,
}


def daily_columns(days: int = 60, sensors: tuple[int, ...] = (1,)) -> dict:
    """센서마다 매일 10시 한 행. 값은 날짜 번호다."""
    n = days * len(sensors)
    slots = np.datetime64("2025-01-01T10:00") + np.tile(
        np.arange(days), len(sensors)
    ) * np.timedelta64(1, "D")
    return {
        "sensor_code": np.repeat(np.array(sensors, dtype=np.int32), days),
        "slot_start": slots.astype("datetime64[s]"),
        "hour_of_day": np.full(n, 10, dtype=np.int8),
        "foot_traffic": np.tile(np.arange(days, dtype=np.float32), len(sensors)),
    }


def test_same_hour_level_is_mean_of_window_ending_gap_days_before() -> None:
    got = recent.recent_levels(daily_columns(), CONFIG)["level_same_hour"]
    # 40일째: 창은 [40-7-27, 40-7] = [6, 33], 값이 날짜 번호라 평균은 19.5
    assert got[40] == pytest.approx(19.5)
    # 표본이 모자란 앞쪽은 NaN (5일째는 창에 날짜가 없다)
    assert np.isnan(got[5]) and np.isnan(got[0])


def test_same_dow_hour_level_uses_same_weekday_weeks_before() -> None:
    got = recent.recent_levels(daily_columns(), CONFIG)["level_same_dow_hour"]
    # 40일째: 7일 간격으로 33, 26, 19, 12, 5 (그 앞은 데이터 없음) → 평균 19
    assert got[40] == pytest.approx(19.0)
    # 표본 2개 미만이면 NaN: 12일째는 5만 있다
    assert np.isnan(got[12])


def test_values_inside_the_gap_do_not_leak() -> None:
    columns = daily_columns()
    base = recent.recent_levels(columns, CONFIG)
    columns["foot_traffic"][38] = (
        10_000.0  # 40일째 예측 시점 기준 2일 전: gap 안이라 못 쓴다.
    )
    changed = recent.recent_levels(columns, CONFIG)
    assert changed["level_same_hour"][40] == base["level_same_hour"][40]
    assert changed["level_same_dow_hour"][40] == base["level_same_dow_hour"][40]


def test_other_sensors_and_hours_are_not_mixed() -> None:
    columns = daily_columns(sensors=(1, 2))
    columns["foot_traffic"][60:] += 1000.0  # 센서 2 는 값이 1000 더 크다.
    got = recent.recent_levels(columns, CONFIG)["level_same_hour"]
    assert got[40] == pytest.approx(19.5)
    assert got[100] == pytest.approx(1019.5)


def test_gap_below_one_day_is_rejected() -> None:
    with pytest.raises(ValueError):
        recent.recent_levels(daily_columns(), {**CONFIG, "gap_days": 0})
