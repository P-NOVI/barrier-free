"""baseline: 센서·요일·시각별 과거 값의 중앙값(또는 평균)."""

from collections.abc import Callable

import numpy as np

HOURS_PER_DAY = 24
SLOTS_PER_WEEK = 7 * HOURS_PER_DAY

STATISTICS: dict[str, Callable[[np.ndarray], float]] = {
    "median": lambda values: float(np.median(values)),
    "mean": lambda values: float(np.mean(values)),
}


def slot_keys(
    sensor_code: np.ndarray, day_of_week: np.ndarray, hour_of_day: np.ndarray
) -> np.ndarray:
    """(센서, 요일, 시각) 하나를 정수 하나로."""
    week_slot = day_of_week.astype(np.int64) * HOURS_PER_DAY + hour_of_day
    return sensor_code.astype(np.int64) * SLOTS_PER_WEEK + week_slot


def fit_baseline(
    keys: np.ndarray, sensors: np.ndarray, y: np.ndarray, statistic: str
) -> tuple[dict[int, float], dict[int, float]]:
    """(센서·요일·시각 → 값, 센서 → 값). 앞의 키가 없을 때 센서 전체 값을 쓴다."""
    summarize = STATISTICS[statistic]
    return group_summary(keys, y, summarize), group_summary(sensors, y, summarize)


def group_summary(
    keys: np.ndarray, y: np.ndarray, summarize: Callable[[np.ndarray], float]
) -> dict[int, float]:
    order = np.argsort(keys, kind="stable")
    unique, starts = np.unique(keys[order], return_index=True)
    groups = np.split(y[order], starts[1:])
    return {int(key): summarize(group) for key, group in zip(unique, groups)}


def predict_baseline(
    keys: np.ndarray,
    sensors: np.ndarray,
    by_slot: dict[int, float],
    by_sensor: dict[int, float],
) -> np.ndarray:
    """키가 없으면 센서 전체 값, 센서도 없으면 0."""
    return np.array(
        [
            by_slot.get(int(key), by_sensor.get(int(sensor), 0.0))
            for key, sensor in zip(keys, sensors)
        ],
        dtype=np.float32,
    )
