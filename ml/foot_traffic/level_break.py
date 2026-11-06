"""센서 수준 단절 감지(시점 기준).

pipeline 13 단계(`level_break`)와 같은 규칙이다. 다른 점은 as_of(학습 종료일) 이후의
데이터를 보지 않는다는 것이다. 이후/이전 구간을 as_of 앞으로 자르므로, 그 시점에 이미
있던 데이터만으로 단절을 판단한다. 비교할 이후 구간에 행이 모자라면 센서를 판단하지
않는다(단절이 아직 관측되지 않은 시점).

clean_break 는 단절 센서 행을 정리한다. 설정에 transition 이 있으면 과도기 행도 빼고,
rescale 이 있으면 단절 전 행을 (센서, 시각)별 계수로 이후 수준에 맞춰 살린다.
"""

from typing import Any

import numpy as np

Columns = dict[str, np.ndarray]
HOURS_PER_DAY = 24


def window_means(
    columns: Columns,
    window: list[str],
    hours: tuple[int, int],
    as_of: np.datetime64,
) -> dict[int, tuple[float, int]]:
    """window([시작, 끝) 날짜)를 as_of 로 자른 안의 낮 시간 센서별 (평균, 행 수)."""
    start = np.datetime64(window[0])
    end = min(np.datetime64(window[1]), as_of)
    if start >= end:
        return {}
    hour = columns["hour_of_day"]
    slot = columns["slot_start"]
    keep = (hour >= hours[0]) & (hour <= hours[1]) & (slot >= start) & (slot < end)
    codes, inverse = np.unique(columns["sensor_code"][keep], return_inverse=True)
    count = np.bincount(inverse)
    total = np.bincount(
        inverse, weights=columns["foot_traffic"][keep].astype(np.float64)
    )
    return {int(c): (float(t / n), int(n)) for c, t, n in zip(codes, total, count)}


def level_ratios(
    columns: Columns, config: dict[str, Any], as_of: np.datetime64
) -> dict[int, float]:
    """센서별 (이후 구간 평균 / 이전 구간 평균). 두 구간에 min_rows 행 이상인 센서만."""
    hours = (config["hour_from"], config["hour_to"])
    before = window_means(columns, config["before"], hours, as_of)
    after = window_means(columns, config["after"], hours, as_of)
    return {
        code: after[code][0] / before[code][0]
        for code in before.keys() & after.keys()
        if min(before[code][1], after[code][1]) >= config["min_rows"]
        and before[code][0] > 0
    }


def flagged_sensors(
    columns: Columns, config: dict[str, Any], as_of: np.datetime64
) -> list[int]:
    """as_of 이전 데이터로 판단한, 수준이 꺾인 센서(이후/이전 < drop_ratio)."""
    ratios = level_ratios(columns, config, as_of)
    return sorted(c for c, ratio in ratios.items() if ratio < config["drop_ratio"])


def keep_after_break(
    columns: Columns, flagged: list[int], config: dict[str, Any]
) -> np.ndarray:
    """단절이 확인된 센서의 break_date 앞 행을 뺀 행 마스크."""
    old = np.isin(columns["sensor_code"], flagged) & (
        columns["slot_start"] < np.datetime64(config["break_date"])
    )
    return ~old


def hour_window_means(
    columns: Columns, window: list[str], as_of: np.datetime64
) -> dict[tuple[int, int], tuple[float, int]]:
    """window([시작, 끝) 날짜)를 as_of 로 자른 안의 (센서, 시각)별 (평균, 행 수)."""
    start = np.datetime64(window[0])
    end = min(np.datetime64(window[1]), as_of)
    if start >= end:
        return {}
    slot = columns["slot_start"]
    keep = (slot >= start) & (slot < end)
    key = columns["sensor_code"][keep].astype(np.int64) * HOURS_PER_DAY + columns[
        "hour_of_day"
    ][keep].astype(np.int64)
    keys, inverse = np.unique(key, return_inverse=True)
    count = np.bincount(inverse)
    total = np.bincount(
        inverse, weights=columns["foot_traffic"][keep].astype(np.float64)
    )
    return {
        (int(k // HOURS_PER_DAY), int(k % HOURS_PER_DAY)): (float(t / n), int(n))
        for k, t, n in zip(keys, total, count)
    }


def hour_factors(
    columns: Columns, flagged: list[int], config: dict[str, Any], as_of: np.datetime64
) -> dict[tuple[int, int], float]:
    """단절 센서의 (센서, 시각)별 보정 계수.

    계수 = (이후/이전) ÷ 대조 센서의 같은 시각 (이후/이전). 이전은 before 구간, 이후는
    rescale.post 구간이고 둘 다 as_of 앞 데이터만 쓴다. 대조는 단절이 아닌 센서의
    비율 중앙값으로, 두 구간의 계절 차이를 덜어 낸다. 두 구간 모두
    min_rows 행 이상인 칸만 계수를 만든다.
    """
    rescale = config["rescale"]
    hours = range(rescale["hour_from"], rescale["hour_to"] + 1)
    before = hour_window_means(columns, config["before"], as_of)
    after = hour_window_means(columns, rescale["post"], as_of)
    ratio = {
        key: after[key][0] / before[key][0]
        for key in before.keys() & after.keys()
        if key[1] in hours
        and min(before[key][1], after[key][1]) >= rescale["min_rows"]
        and before[key][0] > 0
    }
    flagged_set = set(flagged)
    control = {
        hour: float(np.median(values))
        for hour in hours
        if (
            values := [
                r for (c, h), r in ratio.items() if h == hour and c not in flagged_set
            ]
        )
    }
    return {
        (code, hour): r / control[hour]
        for (code, hour), r in ratio.items()
        if code in flagged_set and control.get(hour, 0) > 0
    }


def clean_break(
    columns: Columns, flagged: list[int], config: dict[str, Any], as_of: np.datetime64
) -> tuple[np.ndarray, np.ndarray | None, dict[str, int]]:
    """단절 센서 행 정리 → (남길 행 마스크, 사람 수에 곱할 계수 또는 None, 행 수 통계).

    - transition 이 없으면 기존 규칙(break_date 앞 행 제외)이다.
    - transition 이 있으면 단절 센서의 과도기 [시작, 끝) 행과 그 앞 행을 뺀다.
    - rescale 도 있으면 과도기 앞 행 가운데 계수를 만든 (센서, 시각) 칸은 빼지 않고
      계수를 곱해 이후 수준에 맞춘다(hour_factors). 계수가 없는 칸은 뺀다.
    """
    if "transition" not in config:
        keep = keep_after_break(columns, flagged, config)
        return keep, None, {"rows_dropped": int((~keep).sum()), "rows_rescaled": 0}
    start, end = (np.datetime64(day) for day in config["transition"])
    sensor = np.isin(columns["sensor_code"], flagged)
    slot = columns["slot_start"]
    transition = sensor & (slot >= start) & (slot < end)
    old = sensor & (slot < start)
    keep = ~(transition | old)
    stats = {"rows_transition": int(transition.sum()), "rows_rescaled": 0}
    scale = None
    if config.get("rescale") and flagged:
        factors = hour_factors(columns, flagged, config, as_of)
        if factors:
            key = columns["sensor_code"].astype(np.int64) * HOURS_PER_DAY + columns[
                "hour_of_day"
            ].astype(np.int64)
            table_keys = np.array(
                sorted(c * HOURS_PER_DAY + h for c, h in factors), dtype=np.int64
            )
            table_values = np.array(
                [factors[(k // HOURS_PER_DAY, k % HOURS_PER_DAY)] for k in table_keys]
            )
            position = np.clip(np.searchsorted(table_keys, key), 0, table_keys.size - 1)
            found = old & (table_keys[position] == key)
            scale = np.ones(key.size, dtype=np.float64)
            scale[found] = table_values[position[found]]
            keep |= found
            stats["rows_rescaled"] = int(found.sum())
            stats["factor_median"] = round(float(np.median(table_values)), 4)
    stats["rows_dropped"] = int((~keep).sum())
    return keep, scale, stats
