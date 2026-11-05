"""baseline: 센서·요일·시각별 과거 값의 중앙값(또는 평균)."""

from collections.abc import Callable

import numpy as np

HOURS_PER_DAY = 24
SLOTS_PER_WEEK = 7 * HOURS_PER_DAY

STATISTICS: dict[str, Callable[[np.ndarray], float]] = {
    "median": lambda values: float(np.median(values)),
    "mean": lambda values: float(np.mean(values)),
}
STATISTIC_NAMES = {"median": "중앙값", "mean": "평균", "recent": "최근 수준"}


def reference_level(
    part: dict[str, np.ndarray], fallback: np.ndarray, target_config: dict
) -> np.ndarray:
    """타깃을 나누는 기준값(명/시간). 학습 때와 예측 때 같은 식을 쓴다.

    ratio 면 최근 수준(없으면 fallback)이고 floor 보다 작으면 floor 로 본다. absolute 면
    1 이라 타깃이 사람 수 그대로다. 최근 수준도 fallback 도 없으면 NaN 이다.
    """
    if target_config["mode"] == "absolute":
        return np.ones(part["foot_traffic"].size)
    level = recent_predict(part, fallback).astype(np.float64)
    return np.maximum(level, target_config["floor"])


def recent_predict(part: dict[str, np.ndarray], fallback: np.ndarray) -> np.ndarray:
    """최근 수준 baseline: 같은 요일·시각 최근 평균, 없으면 같은 시각 최근 평균.

    둘 다 없으면 fallback 을 쓴다. 피처 자체를 예측으로 쓰는 단순 규칙이라, 모델이
    이 규칙보다 나아야 최근 수준 피처 위에 학습한 의미가 있다.
    """
    pred = np.where(
        np.isnan(part["level_same_dow_hour"]),
        part["level_same_hour"],
        part["level_same_dow_hour"],
    )
    return np.where(np.isnan(pred), fallback, pred).astype(np.float32)


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
