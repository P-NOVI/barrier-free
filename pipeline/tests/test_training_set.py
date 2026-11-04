import importlib.util
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pyarrow as pa

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
