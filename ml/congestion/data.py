"""학습셋 읽기, 기간 나누기, 피처 행렬 만들기.

학습셋은 pipeline 13 단계 결과(interim/training/hourly.parquet)다.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

Columns = dict[str, np.ndarray]

FLOAT_COLUMNS = ["lon", "lat", "temp", "rain_mm", "visitor_mean", "congestion"]
CALENDAR_COLUMNS = [
    "is_holiday",
    "is_off_day",
    "off_run_length",
    "in_long_holiday",
    "days_to_long_holiday",
    "days_since_long_holiday",
]
UNKNOWN_CATEGORY = -1  # LightGBM 은 음수 범주를 결측으로 본다.


def load_columns(path: Path) -> Columns:
    """학습셋 → 열 이름별 numpy 배열. 결측은 NaN 이다."""
    table = pq.read_table(path)
    columns: Columns = {
        "sensor_code": table["sensor_code"].to_numpy(),
        "district": np.asarray(table["district"].to_pylist(), dtype=object),
        "slot_start": table["slot_start"].to_numpy().astype("datetime64[s]"),
        "day_of_week": table["day_of_week"].to_numpy(),
        "hour_of_day": table["hour_of_day"].to_numpy(),
    }
    for name in FLOAT_COLUMNS + CALENDAR_COLUMNS:
        values = table[name].to_numpy(zero_copy_only=False)
        columns[name] = np.asarray(values, dtype=np.float32)
    return columns


def off_adjacent_flags(is_off_day: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """연속한 날짜별 쉬는 날 여부 → (쉬는 날 전날, 쉬는 날 다음날).

    쉬는 날은 공휴일·주말이다. 쉬는 날 자신은 둘 다 False 이고(금요일은 전날,
    월요일은 다음날이다), 양 끝 날짜는 이웃을 몰라 False 다.
    """
    off = is_off_day.astype(bool)
    next_off = np.append(off[1:], False)
    prev_off = np.insert(off[:-1], 0, False)
    return ~off & next_off, ~off & prev_off


def add_off_adjacent(columns: Columns, calendar_path: Path) -> None:
    """달력(12 단계)으로 is_before_off_day, is_after_off_day 열을 더한다."""
    table = pq.read_table(calendar_path, columns=["date", "is_off_day"])
    dates = table["date"].to_numpy().astype("datetime64[D]")
    if not np.all(np.diff(dates) == np.timedelta64(1, "D")):
        raise ValueError("달력 날짜가 하루씩 이어지지 않습니다.")
    before, after = off_adjacent_flags(
        table["is_off_day"].to_numpy(zero_copy_only=False)
    )
    days = columns["slot_start"].astype("datetime64[D]")
    position = np.searchsorted(dates, days)
    if np.any(position >= len(dates)) or np.any(dates[position] != days):
        raise ValueError("달력이 학습셋 날짜를 덮지 못합니다.")
    columns["is_before_off_day"] = before[position].astype(np.float32)
    columns["is_after_off_day"] = after[position].astype(np.float32)


def take(columns: Columns, mask: np.ndarray) -> Columns:
    return {name: values[mask] for name, values in columns.items()}


def split_masks(slot_start: np.ndarray, split: dict[str, str]) -> dict[str, np.ndarray]:
    """학습·검증·테스트 행 마스크. test_end 는 그날을 포함한다."""
    valid_start = np.datetime64(split["valid_start"])
    test_start = np.datetime64(split["test_start"])
    test_stop = np.datetime64(split["test_end"]) + np.timedelta64(1, "D")
    return {
        "train": slot_start < valid_start,
        "valid": (slot_start >= valid_start) & (slot_start < test_start),
        "test": (slot_start >= test_start) & (slot_start < test_stop),
    }


def make_vocab(columns: Columns, names: list[str]) -> dict[str, list[Any]]:
    """범주형 열의 값 목록(정렬). 위치가 범주 번호가 된다."""
    return {name: sorted(set(columns[name].tolist())) for name in names}


def rain_grade(rain_mm: np.ndarray, bins_mm: list[float]) -> np.ndarray:
    """강수량 → 등급(0 이하 0, 이후 구간마다 1씩). 결측은 NaN."""
    grade = np.digitize(rain_mm, bins_mm, right=True).astype(np.float32)
    grade[np.isnan(rain_mm)] = np.nan
    return grade


def temp_bin(temp: np.ndarray, width_c: float) -> np.ndarray:
    """기온 → width_c 도 폭 구간 번호(아래로 내림)."""
    return np.floor(temp / width_c).astype(np.float32)


def feature_names(config: dict[str, Any], groups: list[str]) -> list[str]:
    return [name for group in groups for name in config["groups"][group]]


def build_features(
    columns: Columns,
    vocab: dict[str, list[Any]],
    config: dict[str, Any],
    groups: list[str],
) -> tuple[np.ndarray, list[str]]:
    """피처 행렬(float32)과 열 이름. 범주형은 vocab 안의 위치 번호로 바꾼다."""
    names = feature_names(config, groups)
    derived = {
        "temp_bin": lambda: temp_bin(columns["temp"], config["temp_bin_c"]),
        "rain_grade": lambda: rain_grade(columns["rain_mm"], config["rain_bins_mm"]),
    }
    matrix = np.empty((len(columns["congestion"]), len(names)), dtype=np.float32)
    for i, name in enumerate(names):
        if name in derived:
            matrix[:, i] = derived[name]()
        elif name in vocab:
            index = {value: n for n, value in enumerate(vocab[name])}
            matrix[:, i] = [
                index.get(value, UNKNOWN_CATEGORY) for value in columns[name].tolist()
            ]
        else:
            matrix[:, i] = columns[name]
    return matrix, names
