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


def outage_rows(columns: dict[str, np.ndarray], config: dict[str, Any]) -> np.ndarray:
    """고장 의심일의 행 마스크.

    센서-날의 낮(hour_from~hour_to) 행이 min_rows 개 이상이고 모두 0 이면 그날
    모든 행이다.

    그날 자신의 값만 보므로 미래 데이터를 쓰지 않는다. 최근 수준 계산에서만 빼고 학습
    행과 0 값은 그대로 둔다.
    """
    hour = columns["hour_of_day"]
    day = columns["slot_start"].astype("datetime64[D]").astype(np.int64)
    key = columns["sensor_code"].astype(np.int64) * (day.max() + 1) + day
    daytime = (hour >= config["hour_from"]) & (hour <= config["hour_to"])
    keys, inverse = np.unique(key, return_inverse=True)
    count = np.bincount(inverse[daytime], minlength=keys.size)
    total = np.bincount(
        inverse[daytime],
        weights=np.abs(columns["foot_traffic"][daytime]).astype(np.float64),
        minlength=keys.size,
    )
    outage = (count >= config["min_rows"]) & (total == 0)
    return outage[inverse]


def dow_hour_values(
    dense: np.ndarray,
    sensor_index: np.ndarray,
    hour: np.ndarray,
    day_index: np.ndarray,
    weeks: list[int],
) -> np.ndarray:
    """행마다 weeks 주 전 같은 요일·시각 값을 모은 (행, 주) 배열. 없는 칸은 NaN."""
    values = np.full((len(day_index), len(weeks)), np.nan)
    for i, week in enumerate(weeks):
        past = day_index - week * DAYS_PER_WEEK
        usable = past >= 0
        values[usable, i] = dense[sensor_index[usable], hour[usable], past[usable]]
    return values


def nan_stat(values: np.ndarray, min_samples: int, statistic: str) -> np.ndarray:
    """행마다 NaN 을 뺀 평균 또는 중앙값. 표본이 min_samples 미만이면 NaN."""
    count = (~np.isnan(values)).sum(axis=1)
    result = np.full(values.shape[0], np.nan)
    ok = count >= min_samples
    reduce = np.nanmedian if statistic == "median" else np.nanmean
    result[ok] = reduce(values[ok], axis=1)
    return result


def extra_levels(
    dense: np.ndarray,
    sensor_index: np.ndarray,
    hour: np.ndarray,
    day_index: np.ndarray,
    gap: int,
    base_same_hour: np.ndarray,
    config: dict[str, Any],
) -> dict[str, np.ndarray]:
    """추가 최근 수준 피처(창은 모두 gap_days 일 전에서 끝난다).

    - level_dow_hour_median: 같은 요일·시각 최근 median_weeks 주 중앙값(이상치에 강하다)
    - level_trend: 같은 시각 최근 short_days 일 평균 ÷ same_hour_days 일 평균
    - level_last_year: 같은 요일·시각의 last_year_weeks 주 전(약 1년 전) 평균
    """
    first_week = -(-gap // DAYS_PER_WEEK)
    recent_weeks = list(range(first_week, first_week + config["median_weeks"]))
    median = nan_stat(
        dow_hour_values(dense, sensor_index, hour, day_index, recent_weeks),
        config["min_samples_median"],
        "median",
    )
    short = same_hour_level(
        dense,
        sensor_index,
        hour,
        day_index,
        gap,
        config["short_days"],
        config["min_samples_short"],
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        trend = np.where(base_same_hour > 0, short / base_same_hour, np.nan)
    last_year = nan_stat(
        dow_hour_values(
            dense, sensor_index, hour, day_index, config["last_year_weeks"]
        ),
        1,
        "mean",
    )
    return {
        "level_dow_hour_median": median.astype(np.float32),
        "level_trend": trend.astype(np.float32),
        "level_last_year": last_year.astype(np.float32),
    }


def recent_levels(
    columns: dict[str, np.ndarray],
    config: dict[str, Any],
    exclude: np.ndarray | None = None,
) -> dict:
    """학습셋 열(sensor_code, slot_start, hour_of_day, foot_traffic) → 최근 수준 열.

    exclude 행(고장 의심일 등)의 값은 평균에 넣지 않는다. config 에 extra 가 있으면
    추가 피처(extra_levels)도 만든다.
    """
    gap = config["gap_days"]
    if gap < 1:
        raise ValueError("gap_days 는 1 이상이어야 합니다(그날 값이 새어 듭니다).")
    hour = columns["hour_of_day"].astype(np.int64)
    values = columns["foot_traffic"].astype(np.float64)
    if exclude is not None:
        values = np.where(exclude, np.nan, values)
    dense, sensor_index, day_index = dense_series(
        columns["sensor_code"], columns["slot_start"], hour, values
    )
    levels = {
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
    if config.get("extra"):
        levels.update(
            extra_levels(
                dense,
                sensor_index,
                hour,
                day_index,
                gap,
                levels["level_same_hour"].astype(np.float64),
                config["extra"],
            )
        )
    return levels
