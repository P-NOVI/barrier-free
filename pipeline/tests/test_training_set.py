import importlib.util
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

STEPS = Path(__file__).resolve().parents[1] / "steps"
BINS_PER_HOUR = 6


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


training = load_step("13_build_training_set.py")


def stamps(*texts: str) -> np.ndarray:
    return np.array(texts, dtype="datetime64[ms]")


def test_hour_end_groups_by_interval_end() -> None:
    got = training.hour_end(
        stamps("2024-01-01T00:10", "2024-01-01T01:00", "2024-01-01T01:10")
    )
    assert got.tolist() == [
        datetime(2024, 1, 1, 1),
        datetime(2024, 1, 1, 1),
        datetime(2024, 1, 1, 2),
    ]


def history_table(times: list[str], counts: list[int]) -> pa.Table:
    return pa.table(
        {
            "sensor_code": pa.array([1] * len(times), type=pa.int32()),
            "measured_at": pa.array(stamps(*times), type=pa.timestamp("ms")),
            "visitor_count": pa.array(counts, type=pa.int32()),
        }
    )


def test_aggregate_hourly_sums_to_people_per_hour_and_drops_short_hours() -> None:
    full = [f"2024-01-01T00:{m:02d}" for m in (10, 20, 30, 40, 50)] + [
        "2024-01-01T01:00"
    ]
    short = ["2024-01-01T01:10", "2024-01-01T01:20", "2024-01-01T01:30"]
    table, dropped = training.aggregate_hourly(
        history_table(full + short, [10, 20, 30, 40, 50, 60, 5, 5, 5]),
        min_bins=4,
        bins_per_hour=BINS_PER_HOUR,
    )
    assert dropped == 1
    assert table["hour_end"].to_pylist() == [datetime(2024, 1, 1, 1)]
    # 10분 값 6개의 합 = 평균 35 × 6
    assert table["foot_traffic"].to_pylist() == [210.0]
    assert table["bins"].to_pylist() == [6]


def test_missing_bins_are_scaled_to_a_full_hour() -> None:
    times = [f"2024-01-01T00:{m:02d}" for m in (10, 20, 30, 40)]
    table, _ = training.aggregate_hourly(
        history_table(times, [10, 10, 20, 20]), 4, BINS_PER_HOUR
    )
    # 4개 평균 15 × 6
    assert table["foot_traffic"].to_pylist() == [90.0]


BREAK_CONFIG = {
    "break_date": "2025-09-01",
    "before": ["2025-03-01", "2025-08-01"],
    "after": ["2025-10-01", "2026-06-01"],
    "hour_from": 9,
    "hour_to": 14,
    "min_rows": 3,
    "drop_ratio": 0.7,
    "rise_ratio": 1.3,
}


def traffic_table(rows: list[tuple[int, str, float]]) -> pa.Table:
    """(센서, 구간 시작 시각, 유동인구) → 13단계 hourly 표(hour_end 는 한 시간 뒤)."""
    starts = np.array([r[1] for r in rows], dtype="datetime64[s]")
    return pa.table(
        {
            "sensor_code": pa.array([r[0] for r in rows], type=pa.int32()),
            "hour_end": pa.array(
                starts + np.timedelta64(1, "h"), type=pa.timestamp("s")
            ),
            "foot_traffic": pa.array([r[2] for r in rows], type=pa.float32()),
        }
    )


def level_break_rows() -> list[tuple[int, str, float]]:
    rows = []
    for day in range(1, 6):
        before, after = f"2025-04-0{day}T10:00", f"2025-11-0{day}T10:00"
        rows += [(1, before, 2000.0), (1, after, 1000.0)]  # 절반으로 하락
        rows += [(2, before, 2000.0), (2, after, 1900.0)]  # 거의 그대로
        rows += [(4, before, 1000.0), (4, after, 1500.0)]  # 1.5배 상승
    rows.append((1, "2025-08-20T10:00", 500.0))  # 단절 구간의 불안정한 값
    rows.append((3, "2025-04-01T10:00", 2000.0))  # 이후 구간 행이 모자란 센서
    rows.append((3, "2025-11-01T10:00", 100.0))
    return rows


def test_level_ratios_use_daytime_windows_and_min_rows() -> None:
    ratios = training.level_ratios(traffic_table(level_break_rows()), BREAK_CONFIG)
    assert ratios == {1: 0.5, 2: 0.95, 4: 1.5}  # 센서 3 은 행이 모자라 비교하지 않는다.


def test_level_ratios_ignore_night_hours() -> None:
    rows = [(1, f"2025-04-0{d}T02:00", 5000.0) for d in range(1, 6)]
    rows += [(1, f"2025-11-0{d}T02:00", 10.0) for d in range(1, 6)]
    assert training.level_ratios(traffic_table(rows), BREAK_CONFIG) == {}


def test_drop_before_level_break_only_for_dropped_sensors() -> None:
    hourly = traffic_table(level_break_rows())
    ratios = training.level_ratios(hourly, BREAK_CONFIG)
    kept, flagged, dropped = training.drop_before_level_break(
        hourly, ratios, BREAK_CONFIG
    )
    assert flagged == [1]
    # 센서 1 의 이전 구간 5행과 단절 구간 1행
    assert dropped == 6
    assert kept.num_rows == hourly.num_rows - 6
    sensor_1 = kept.filter(pa.array(kept["sensor_code"].to_numpy() == 1))
    assert set(sensor_1["foot_traffic"].to_pylist()) == {1000.0}


def test_keep_majority_district_drops_other_district_rows() -> None:
    history = pa.table(
        {
            "sensor_code": pa.array([1, 1, 1, 2, 2], type=pa.int32()),
            "district": ["Seocho-gu", "Seocho-gu", "Guro-gu", "Jung-gu", "Mapo-gu"],
            "visitor_count": [1, 2, 3, 4, 5],
        }
    )
    districts = training.majority_districts(history)
    # 센서 2 는 한 번씩이라 이름이 앞서는 Jung-gu
    assert districts == {1: "Seocho-gu", 2: "Jung-gu"}
    kept = training.keep_majority_district(history, districts)
    assert sorted(kept["visitor_count"].to_pylist()) == [1, 2, 4]


def test_zero_counts_stay_zero() -> None:
    times = [f"2024-01-01T00:{m:02d}" for m in (10, 20, 30, 40)]
    table, _ = training.aggregate_hourly(
        history_table(times, [0, 0, 0, 0]), 4, BINS_PER_HOUR
    )
    assert table["foot_traffic"].to_pylist() == [0.0]


def test_build_training_set_joins_without_normalizing() -> None:
    hourly = pa.table(
        {
            "sensor_code": pa.array([1, 1], type=pa.int32()),
            # 2024-01-01 00:00 이 끝인 구간 = 2023-12-31 23:00 시작(전날)
            "hour_end": pa.array(
                np.array(
                    ["2024-01-01T00:00", "2024-01-01T01:00"], dtype="datetime64[s]"
                ),
                type=pa.timestamp("s"),
            ),
            "foot_traffic": pa.array([50.0, 300.0], type=pa.float32()),
        }
    )
    weather = pa.table(
        {
            "district": ["Gangnam-gu"] * 2,
            "hour": pa.array(
                np.array(
                    ["2024-01-01T00:00", "2024-01-01T01:00"], dtype="datetime64[s]"
                ),
                type=pa.timestamp("s"),
            ),
            "temp": pa.array([-3.0, -4.0], type=pa.float32()),
            "rain_mm": pa.array([0.0, 1.5], type=pa.float32()),
        }
    )
    columns = training.CALENDAR_COLUMNS
    calendar = pa.table(
        {
            "date": pa.array([date(2023, 12, 31), date(2024, 1, 1)], type=pa.date32()),
            **{
                name: pa.array([False, True] if name.startswith("is_") else [0, 1])
                for name in columns
            },
        }
    )
    table = training.build_training_set(
        hourly,
        {1: "Gangnam-gu"},
        {1: (127.0, 37.5)},
        weather,
        calendar,
    )
    rows = table.to_pylist()
    first, second = rows
    # 첫 행은 slot_start 가 12-31 23시라 달력은 12-31(휴일 아님), 날씨는 구간 끝 00시 값
    assert first["slot_start"] == datetime(2023, 12, 31, 23)
    assert first["day_of_week"] == 6  # 일요일
    assert first["hour_of_day"] == 23
    assert first["is_holiday"] is False
    assert first["rain_mm"] == 0.0 and first["temp"] == -3.0
    # 유동인구는 센서 값 그대로다.
    assert first["foot_traffic"] == 50.0
    # 둘째 행은 slot_start 가 01-01 00시, 비 1.5mm
    assert second["is_holiday"] is True
    assert second["rain_mm"] == 1.5
    assert second["foot_traffic"] == 300.0
    assert second["district"] == "Gangnam-gu"


def test_sensor_stations_within_radius() -> None:
    stations = pa.table(
        {
            "line": ["1호선", "2호선", "3호선"],
            "station": ["가", "가", "나"],
            "lon": [127.0000, 127.0030, 127.0300],
            "lat": [37.5000, 37.5000, 37.5000],
        }
    )
    near = training.sensor_stations({1: (127.0, 37.5), 2: (126.9, 37.5)}, stations, 500)
    assert near.to_pylist() == [
        {"sensor_code": 1, "line": "1호선", "station": "가"},
        {"sensor_code": 1, "line": "2호선", "station": "가"},
    ]


def test_daily_ridership_divides_by_days_in_month() -> None:
    subway = pa.table(
        {
            "month": ["2024-02", "2023-04"],
            "line": ["1호선", "1호선"],
            "station": ["가", "가"],
            "hour": pa.array([8, 8], type=pa.int8()),
            "boardings": pa.array([290, 300], type=pa.int32()),
            "alightings": pa.array([58, 60], type=pa.int32()),
        }
    )
    daily = training.daily_ridership(subway)
    assert daily["boardings"].to_pylist() == pytest.approx([10.0, 10.0])
    assert daily["alightings"].to_pylist() == pytest.approx([2.0, 2.0])


def test_add_subway_uses_last_year_and_fills_zero_or_null() -> None:
    near = pa.table(
        {
            "sensor_code": pa.array([1, 1], type=pa.int32()),
            "line": ["1호선", "2호선"],
            "station": ["가", "가"],
        }
    )
    daily = pa.table(
        {
            "line": ["1호선", "2호선", "1호선"],
            "station": ["가", "가", "가"],
            "month": ["2023-03", "2023-03", "2023-03"],
            "hour": pa.array([8, 8, 9], type=pa.int8()),
            "boardings": [10.0, 5.0, 7.0],
            "alightings": [1.0, 2.0, 3.0],
        }
    )
    table = pa.table(
        {
            "sensor_code": pa.array([1, 1, 2, 1], type=pa.int32()),
            "slot_start": pa.array(
                stamps(
                    "2024-03-04T08:00",
                    "2024-03-04T10:00",
                    "2024-03-04T08:00",
                    "2024-01-04T08:00",
                ),
                type=pa.timestamp("s"),
            ),
            "hour_of_day": pa.array([8, 10, 8, 8], type=pa.int8()),
            "foot_traffic": pa.array([10.0, 20.0, 30.0, 40.0], type=pa.float32()),
        }
    )
    out = training.add_subway(
        table, training.subway_features(near, daily), ["2023-02", "2023-03"], 12
    )
    # 원래 열 뒤에 승하차 열을 붙인다.
    assert out.column_names == [
        "sensor_code",
        "slot_start",
        "hour_of_day",
        "foot_traffic",
        "subway_boardings",
        "subway_alightings",
    ]
    rows = [
        (r["sensor_code"], r["hour_of_day"], r["subway_boardings"])
        for r in out.to_pylist()
    ]
    # 두 호선을 더한다. 그 시각 자료가 없거나 역이 없는 센서는 0,
    # 자료가 없는 달(2023-01)은 null 이다.
    assert rows == [(1, 8, None), (1, 8, 15.0), (1, 10, 0.0), (2, 8, 0.0)]
