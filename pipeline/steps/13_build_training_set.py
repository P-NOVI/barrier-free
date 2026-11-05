"""S-DoT 유동인구 예측 모델의 학습셋 training/hourly.parquet 을 만든다.

실행: pipeline/ 에서 uv run python steps/13_build_training_set.py
- 입력: interim/sdot/history.parquet (06 단계, 10분 단위 유동인구)
        interim/weather/hourly.parquet (11 단계, 자치구·시간별 기온·강수)
        interim/calendar/daily.parquet (12 단계, 날짜별 공휴일·연휴)
        data/processed/sdot_sensors.json (센서 위치)
- 출력: interim/training/hourly.parquet, hourly_report.json
  열: sensor_code, district, lon, lat, slot_start, day_of_week, hour_of_day, temp,
      rain_mm, 달력 열 6개(12 단계와 같은 이름), foot_traffic
시각
- measured_at 은 구간 끝 시각이다. (H-1:00, H:00] 의 10분 값을 묶어 한 시간 H 로
  만든다.
- slot_start 는 그 한 시간의 시작(H-1:00)이다. 요일·시각·날짜(달력)는 slot_start 로
  구한다.
- 날씨는 H 정시 행을 그대로 붙인다. 강수량이 직전 1시간 누적이라 한 시간 구간과 맞는다.
처리
- foot_traffic 은 한 시간에 센서를 지나간 사람 수(명/시간)다. 한 시간 안 10분 값의
  평균에 bins_per_hour 를 곱한다. 10분 값이 min_bins 개 미만인 시간은 버린다.
- 센서 값은 그대로 쓰고 정규화하지 않는다. 0 은 낮에도 그대로 둔다(사람이 안
  지나갔을 수 있다).
- 센서의 자치구는 가장 많이 기록된 하나다. 다른 자치구로 기록된 행(자치구가 잘못
  찍힌 주, 센서를 옮기기 전 구간)은 버리고 개수를 보고서에 남긴다.
- 2025-08 전후로 평균 유동인구가 크게 꺾인 센서(수집 방식이 바뀐 것으로 보인다)는 그
  전 구간을 뺀다. level_break 의 낮 시간(hour_from ~ hour_to) 평균을 이전 구간과 이후
  구간으로 비교해 이후/이전이 drop_ratio 미만이면 break_date 앞 행을 버린다. 값이
  오른 센서는 버리지 않고 보고서에만 남긴다.
- 날씨가 없는 칸(강수 결측 등)은 NaN 으로 둔다.
학습·검증·테스트 나누기는 ml/ 에서 한다.
그래프(00~04 단계)와 관계가 없어서 run_all.py 에 넣지 않고 따로 실행한다.
"""

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from common import CONFIG_PATH, data_path, load_config, repo_path, require_files

PARQUET_COMPRESSION = "zstd"
CALENDAR_COLUMNS = [
    "is_holiday",
    "is_off_day",
    "off_run_length",
    "in_long_holiday",
    "days_to_long_holiday",
    "days_since_long_holiday",
]
HOUR = np.timedelta64(1, "h")
TRAFFIC_QUANTILES = (0.5, 0.95, 0.99)


def hour_end(measured_at: np.ndarray) -> np.ndarray:
    """구간 끝 시각 → 그 시각이 속한 한 시간 (H-1:00, H:00] 의 끝 정시 H."""
    minutes_since_epoch = measured_at.astype("datetime64[m]").astype(np.int64)
    minutes_per_hour = 60
    ceil_hours = -(-minutes_since_epoch // minutes_per_hour)
    return ceil_hours.astype("datetime64[h]").astype("datetime64[s]")


def aggregate_hourly(
    history: pa.Table, min_bins: int, bins_per_hour: int
) -> tuple[pa.Table, int]:
    """10분 값을 센서·시간별 유동인구(명/시간)로 묶는다.

    10분 값이 빠진 시간은 있는 값의 평균을 bins_per_hour 개로 늘려 한 시간치로 본다.
    반환: (열 sensor_code, hour_end, foot_traffic, bins 의 표,
    10분 값이 모자라 버린 시간 수)
    """
    ends = hour_end(history["measured_at"].to_numpy())
    grouped = (
        pa.table(
            {
                "sensor_code": history["sensor_code"],
                "hour_end": pa.array(ends, type=pa.timestamp("s")),
                "visitor_count": history["visitor_count"],
            }
        )
        .group_by(["sensor_code", "hour_end"])
        .aggregate([("visitor_count", "sum"), ("visitor_count", "count")])
    )
    bins = grouped["visitor_count_count"].to_numpy()
    keep = bins >= min_bins
    total = grouped["visitor_count_sum"].to_numpy()
    table = pa.table(
        {
            "sensor_code": grouped["sensor_code"].to_numpy()[keep],
            "hour_end": pa.array(
                grouped["hour_end"].to_numpy()[keep], type=pa.timestamp("s")
            ),
            "foot_traffic": (total[keep] / bins[keep] * bins_per_hour).astype(
                np.float32
            ),
            "bins": bins[keep],
        }
    )
    return table, int((~keep).sum())


def read_sensor_places(path: Path) -> dict[int, tuple[float, float]]:
    """센서 코드 → (경도, 위도)."""
    sensors = json.loads(path.read_text(encoding="utf-8"))["sensors"]
    return {s["code"]: (s["lon"], s["lat"]) for s in sensors}


def majority_districts(history: pa.Table) -> dict[int, str]:
    """센서 코드 → 가장 많이 기록된 자치구. 같은 수면 이름이 앞서는 쪽."""
    counts = (
        history.filter(pc.is_valid(history["district"]))
        .group_by(["sensor_code", "district"])
        .aggregate([("district", "count")])
        .sort_by(
            [
                ("sensor_code", "ascending"),
                ("district_count", "descending"),
                ("district", "ascending"),
            ]
        )
    )
    districts: dict[int, str] = {}
    for code, district in zip(
        counts["sensor_code"].to_pylist(), counts["district"].to_pylist()
    ):
        districts.setdefault(code, district)
    return districts


def keep_majority_district(history: pa.Table, districts: dict[int, str]) -> pa.Table:
    """센서의 최다 자치구가 아닌 자치구로 기록된 행을 뺀다."""
    keep = pa.table(
        {
            "sensor_code": pa.array(list(districts), type=pa.int32()),
            "district": pa.array(list(districts.values()), type=pa.string()),
        }
    )
    return history.join(keep, keys=["sensor_code", "district"], join_type="left semi")


def slot_starts(hourly: pa.Table) -> np.ndarray:
    """한 시간 구간의 시작 시각(H-1:00)."""
    return hourly["hour_end"].to_numpy() - HOUR.astype("timedelta64[s]")


def window_means(
    hourly: pa.Table, window: list[str], hours: tuple[int, int]
) -> dict[int, tuple[float, int]]:
    """window([시작, 끝) 날짜) 안 낮 시간(hours 포함)의 센서별 (평균, 행 수)."""
    slot_start = slot_starts(hourly)
    hour_of_day = slot_start.astype("datetime64[h]").astype(np.int64) % 24
    keep = (
        (hour_of_day >= hours[0])
        & (hour_of_day <= hours[1])
        & (slot_start >= np.datetime64(window[0]))
        & (slot_start < np.datetime64(window[1]))
    )
    codes, inverse = np.unique(
        hourly["sensor_code"].to_numpy()[keep], return_inverse=True
    )
    count = np.bincount(inverse)
    total = np.bincount(
        inverse, weights=hourly["foot_traffic"].to_numpy()[keep].astype(np.float64)
    )
    return {int(c): (float(t / n), int(n)) for c, t, n in zip(codes, total, count)}


def level_ratios(hourly: pa.Table, config: dict[str, Any]) -> dict[int, float]:
    """센서별 (이후 구간 평균 / 이전 구간 평균). 두 구간에 min_rows 행 이상인 센서만."""
    hours = (config["hour_from"], config["hour_to"])
    before = window_means(hourly, config["before"], hours)
    after = window_means(hourly, config["after"], hours)
    return {
        code: after[code][0] / before[code][0]
        for code in before.keys() & after.keys()
        if min(before[code][1], after[code][1]) >= config["min_rows"]
        and before[code][0] > 0
    }


def drop_before_level_break(
    hourly: pa.Table, ratios: dict[int, float], config: dict[str, Any]
) -> tuple[pa.Table, list[int], int]:
    """이후/이전이 drop_ratio 미만인 센서의 break_date 앞 행을 뺀다.

    반환: (남은 표, 해당 센서 코드, 버린 행 수)
    """
    flagged = sorted(c for c, ratio in ratios.items() if ratio < config["drop_ratio"])
    old = np.isin(hourly["sensor_code"].to_numpy(), flagged) & (
        slot_starts(hourly) < np.datetime64(config["break_date"])
    )
    return hourly.filter(pa.array(~old)), flagged, int(old.sum())


def build_training_set(
    hourly: pa.Table,
    districts: dict[int, str],
    places: dict[int, tuple[float, float]],
    weather: pa.Table,
    calendar: pa.Table,
) -> pa.Table:
    """센서·시간별 유동인구에 센서 정보, 날씨, 달력을 붙인다."""
    codes = hourly["sensor_code"].to_numpy()
    slot_start = pa.array(
        hourly["hour_end"].to_numpy() - HOUR.astype("timedelta64[s]"),
        type=pa.timestamp("s"),
    )
    table = pa.table(
        {
            "sensor_code": hourly["sensor_code"],
            "district": pa.array([districts[int(c)] for c in codes]),
            "lon": pa.array([places[int(c)][0] for c in codes], type=pa.float32()),
            "lat": pa.array([places[int(c)][1] for c in codes], type=pa.float32()),
            "hour_end": hourly["hour_end"],
            "slot_start": slot_start,
            "date": pc.cast(slot_start, pa.date32()),
            "day_of_week": pc.cast(pc.day_of_week(slot_start), pa.int8()),
            "hour_of_day": pc.cast(pc.hour(slot_start), pa.int8()),
            "foot_traffic": hourly["foot_traffic"],
        }
    )
    weather = weather.rename_columns(["district", "hour_end", "temp", "rain_mm"])
    weather = weather.set_column(
        1, "hour_end", pc.cast(weather["hour_end"], pa.timestamp("s"))
    )
    table = table.join(
        weather,
        keys=["district", "hour_end"],
        join_type="left outer",
    )
    table = table.join(
        calendar.select(["date", *CALENDAR_COLUMNS]),
        keys="date",
        join_type="left outer",
    )
    names = [
        "sensor_code",
        "district",
        "lon",
        "lat",
        "slot_start",
        "day_of_week",
        "hour_of_day",
        "temp",
        "rain_mm",
        *CALENDAR_COLUMNS,
        "foot_traffic",
    ]
    return table.select(names).sort_by(
        [("sensor_code", "ascending"), ("slot_start", "ascending")]
    )


def count_missing(column: pa.ChunkedArray) -> int:
    """null(조인에서 못 찾음)과 NaN(날씨 원본 결측)의 합."""
    return int(column.null_count + np.isnan(column.fill_null(0.0).to_numpy()).sum())


def make_report(table: pa.Table, dropped: dict[str, Any]) -> dict[str, Any]:
    traffic = table["foot_traffic"].to_numpy()
    hour_of_day = table["hour_of_day"].to_numpy()
    zero = traffic == 0
    return {
        "rows": table.num_rows,
        "sensors": len(set(table["sensor_code"].to_pylist())),
        "first_slot": pc.min(table["slot_start"]).as_py().isoformat(),
        "last_slot": pc.max(table["slot_start"]).as_py().isoformat(),
        **dropped,
        "zero_share": round(float(zero.mean()), 4),
        "zero_share_by_hour": {
            int(h): round(float(zero[hour_of_day == h].mean()), 4) for h in range(24)
        },
        "foot_traffic_mean": round(float(traffic.mean()), 2),
        "foot_traffic_max": round(float(traffic.max()), 1),
        "foot_traffic_quantiles": {
            str(q): round(float(np.quantile(traffic, q)), 1) for q in TRAFFIC_QUANTILES
        },
        "missing_temp": count_missing(table["temp"]),
        "missing_rain_mm": count_missing(table["rain_mm"]),
        "missing_calendar": int(table["is_holiday"].null_count),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["training_set"]
    history_path = data_path(config["history"])
    weather_path = data_path(config["weather"])
    calendar_path = data_path(config["calendar"])
    sensors_path = repo_path(config["sensors"])
    output = data_path(config["output"])
    report_path = data_path(config["report"])
    require_files(history_path, weather_path, calendar_path, sensors_path)

    started = time.time()
    weather = pq.read_table(weather_path)
    calendar = pq.read_table(calendar_path)
    history = pq.read_table(
        history_path,
        columns=["sensor_code", "measured_at", "visitor_count", "district"],
    )
    districts = majority_districts(history)
    rows_before = history.num_rows
    history = keep_majority_district(history, districts)
    rows_other_district = rows_before - history.num_rows
    places = read_sensor_places(sensors_path)
    no_place = sorted(set(districts) - set(places))

    # 날씨가 있는 시간(구간 끝 H 가 날씨 첫 시각 이후)만 쓴다.
    first_hour = np.datetime64(pc.min(weather["hour"]).as_py(), "s")
    last_hour = np.datetime64(pc.max(weather["hour"]).as_py(), "s")
    hourly, short_hours = aggregate_hourly(
        history, config["min_bins"], config["bins_per_hour"]
    )
    ends = hourly["hour_end"].to_numpy()
    in_weather = (ends >= first_hour) & (ends <= last_hour)
    located = np.isin(hourly["sensor_code"].to_numpy(), list(places))
    hourly = hourly.filter(pa.array(in_weather & located))

    break_config = config["level_break"]
    ratios = level_ratios(hourly, break_config)
    hourly, flagged, rows_before_break = drop_before_level_break(
        hourly, ratios, break_config
    )
    level_break = {
        "break_date": break_config["break_date"],
        "flagged_sensors": flagged,
        "rows_dropped": rows_before_break,
        "flagged_ratios": {str(c): round(ratios[c], 3) for c in flagged},
        "rising_sensors": sorted(
            c for c, ratio in ratios.items() if ratio > break_config["rise_ratio"]
        ),
        "compared_sensors": len(ratios),
    }

    table = build_training_set(hourly, districts, places, weather, calendar)
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, output, compression=PARQUET_COMPRESSION)

    dropped = {
        "rows_dropped_other_district": rows_other_district,
        "hours_dropped_few_bins": short_hours,
        "sensors_without_location": no_place,
        "level_break": level_break,
    }
    report = make_report(table, dropped)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"행 {table.num_rows:,}, 센서 {report['sensors']}개, "
        f"결측 기온 {report['missing_temp']:,} 강수 {report['missing_rain_mm']:,} "
        f"→ {output} ({output.stat().st_size / 1e6:.1f} MB, "
        f"{time.time() - started:.0f}s)",
        flush=True,
    )
    print(f"보고서 {report_path}", flush=True)


if __name__ == "__main__":
    main()
