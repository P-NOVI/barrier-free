"""센서의 최근 수준 피처: 예측 시점보다 gap 일 앞까지의 평균 유동인구.

- level_same_hour: 같은 시각(요일 무관)의 최근 same_hour_days 일 평균
- level_same_dow_hour: 같은 요일·같은 시각의 최근 same_dow_weeks 주 평균
창은 모두 예측하려는 날의 gap_days 일 전에서 끝난다. 서비스에서 예측을 돌릴 때 이미
가진 센서 데이터만 쓰게 하려는 장치로, gap_days 가 1 미만이면 그날 값이 새어 든다.
표본이 모자라면 NaN 이다.
"""

from typing import Any

import numpy as np

HOURS_PER_DAY = 24
DAYS_PER_WEEK = 7


def dense_series(
    sensor_code: np.ndarray,
    slot_start: np.ndarray,
    hour_of_day: np.ndarray,
    foot_traffic: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(센서, 시각, 날짜) 배열. 값이 없는 칸은 NaN.

    반환: (배열, 행별 센서 번호, 행별 날짜 번호). 센서·시각·날짜마다 행은 하나다.
    """
    codes, sensor_index = np.unique(sensor_code, return_inverse=True)
    days = slot_start.astype("datetime64[D]")
    day_index = (days - days.min()).astype(np.int64)
    dense = np.full(
        (len(codes), HOURS_PER_DAY, int(day_index.max()) + 1), np.nan, dtype=np.float64
    )
    dense[sensor_index, hour_of_day.astype(np.int64), day_index] = foot_traffic
    return dense, sensor_index, day_index


def same_hour_level(
    dense: np.ndarray,
    sensor_index: np.ndarray,
    hour: np.ndarray,
    day_index: np.ndarray,
    gap_days: int,
    window_days: int,
    min_samples: int,
) -> np.ndarray:
    """같은 시각의 [날짜 - gap_days - window_days + 1, 날짜 - gap_days] 평균."""
    n_days = dense.shape[2]
    zeros = np.zeros(dense.shape[:2] + (1,))
    total = np.concatenate([zeros, np.cumsum(np.nan_to_num(dense), axis=2)], axis=2)
    count = np.concatenate([zeros, np.cumsum(~np.isnan(dense), axis=2)], axis=2)
    end = day_index - gap_days + 1  # 창의 끝(포함하지 않는 쪽)
    high = np.clip(end, 0, n_days)
    low = np.clip(end - window_days, 0, n_days)
    window_total = total[sensor_index, hour, high] - total[sensor_index, hour, low]
    window_count = count[sensor_index, hour, high] - count[sensor_index, hour, low]
    return np.where(
        window_count >= min_samples, window_total / np.maximum(window_count, 1), np.nan
    )


def same_dow_hour_level(
    dense: np.ndarray,
    sensor_index: np.ndarray,
    hour: np.ndarray,
    day_index: np.ndarray,
    gap_days: int,
    weeks: int,
    min_samples: int,
) -> np.ndarray:
    """같은 요일·시각의 gap_days 이전 주 가운데 최근 weeks 주 평균."""
    first_week = -(-gap_days // DAYS_PER_WEEK)  # gap 보다 먼저 끝나는 첫 주(올림)
    total = np.zeros(len(day_index))
    count = np.zeros(len(day_index))
    for week in range(first_week, first_week + weeks):
        past = day_index - week * DAYS_PER_WEEK
        usable = past >= 0
        value = np.full(len(day_index), np.nan)
        value[usable] = dense[sensor_index[usable], hour[usable], past[usable]]
        found = ~np.isnan(value)
        total[found] += value[found]
        count[found] += 1
    return np.where(count >= min_samples, total / np.maximum(count, 1), np.nan)


def recent_levels(columns: dict[str, np.ndarray], config: dict[str, Any]) -> dict:
    """학습셋 열(sensor_code, slot_start, hour_of_day, foot_traffic) → 최근 수준 열."""
    gap = config["gap_days"]
    if gap < 1:
        raise ValueError("gap_days 는 1 이상이어야 합니다(그날 값이 새어 듭니다).")
    hour = columns["hour_of_day"].astype(np.int64)
    dense, sensor_index, day_index = dense_series(
        columns["sensor_code"], columns["slot_start"], hour, columns["foot_traffic"]
    )
    return {
        "level_same_hour": same_hour_level(
            dense,
            sensor_index,
            hour,
            day_index,
            gap,
            config["same_hour_days"],
            config["min_samples_hour"],
        ).astype(np.float32),
        "level_same_dow_hour": same_dow_hour_level(
            dense,
            sensor_index,
            hour,
            day_index,
            gap,
            config["same_dow_weeks"],
            config["min_samples_dow"],
        ).astype(np.float32),
    }
