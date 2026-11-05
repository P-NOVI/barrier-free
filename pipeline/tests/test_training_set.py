import importlib.util
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

STEPS = Path(__file__).resolve().parents[1] / "steps"


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


def test_aggregate_hourly_averages_and_drops_short_hours() -> None:
    full = [f"2024-01-01T00:{m:02d}" for m in (10, 20, 30, 40, 50)] + [
        "2024-01-01T01:00"
    ]
    short = ["2024-01-01T01:10", "2024-01-01T01:20", "2024-01-01T01:30"]
    table, dropped = training.aggregate_hourly(
        history_table(full + short, [10, 20, 30, 40, 50, 60, 5, 5, 5]), min_bins=4
    )
    assert dropped == 1
    assert table["hour_end"].to_pylist() == [datetime(2024, 1, 1, 1)]
    assert table["visitor_mean"].to_pylist() == [35.0]
    assert table["bins"].to_pylist() == [6]


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
    table, _ = training.aggregate_hourly(history_table(times, [0, 0, 0, 0]), 4)
    assert table["visitor_mean"].to_pylist() == [0.0]


def test_sensor_scales_use_train_period_only() -> None:
    codes = np.array([1, 1, 1, 1, 2, 2])
    slots = stamps(
        "2024-01-01T10:00",
        "2024-01-02T10:00",
        "2024-01-02T11:00",
        "2026-08-01T10:00",  # 학습 기간 밖: 기준값에 들어가지 않는다.
        "2024-01-01T10:00",
        "2024-01-01T11:00",
    ).astype("datetime64[s]")
    means = np.array([0.0, 10.0, 20.0, 1000.0, 3.0, 5.0], dtype=np.float32)
    scales = training.sensor_scales(
        codes, slots, means, "2024-01-01", "2026-07-31", quantile=0.5
    )
    assert scales == {1: 10.0, 2: 4.0}


def test_build_training_set_joins_and_normalizes() -> None:
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
            "visitor_mean": pa.array([5.0, 30.0], type=pa.float32()),
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
        {1: 10.0},
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
    assert first["congestion"] == 0.5
    # 둘째 행은 slot_start 가 01-01 00시, 비 1.5mm, 30/10 은 1 로 자른다.
    assert second["is_holiday"] is True
    assert second["rain_mm"] == 1.5
    assert second["congestion"] == 1.0
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
            "visitor_mean": pa.array([1.0, 2.0, 3.0, 4.0], type=pa.float32()),
            "congestion": pa.array([0.1, 0.2, 0.3, 0.4], type=pa.float32()),
        }
    )
    out = training.add_subway(
        table, training.subway_features(near, daily), ["2023-02", "2023-03"], 12
    )
    assert out.column_names == [
        "sensor_code",
        "slot_start",
        "hour_of_day",
        "subway_boardings",
        "subway_alightings",
        "visitor_mean",
        "congestion",
    ]
    rows = [
        (r["sensor_code"], r["hour_of_day"], r["subway_boardings"])
        for r in out.to_pylist()
    ]
    # 두 호선을 더한다. 그 시각 자료가 없거나 역이 없는 센서는 0,
    # 자료가 없는 달(2023-01)은 null 이다.
    assert rows == [(1, 8, None), (1, 8, 15.0), (1, 10, 0.0), (2, 8, 0.0)]
