"""S-DoT 혼잡도 예측 모델의 학습셋 training/hourly.parquet 을 만든다.

실행: pipeline/ 에서 uv run python steps/13_build_training_set.py
- 입력: interim/sdot/history.parquet (06 단계, 10분 단위 유동인구)
        interim/weather/hourly.parquet (11 단계, 자치구·시간별 기온·강수)
        interim/calendar/daily.parquet (12 단계, 날짜별 공휴일·연휴)
        data/processed/sdot_sensors.json (센서 위치)
- 출력: interim/training/hourly.parquet, sensor_scale.json, hourly_report.json
  열: sensor_code, district, lon, lat, slot_start, day_of_week, hour_of_day, temp,
      rain_mm, 달력 열 6개(12 단계와 같은 이름), visitor_mean, congestion
시각
- measured_at 은 구간 끝 시각이다. (H-1:00, H:00] 의 10분 값을 묶어 한 시간 H 로
  만든다.
- slot_start 는 그 한 시간의 시작(H-1:00)이다. 요일·시각·날짜(달력)는 slot_start 로
  구한다.
- 날씨는 H 정시 행을 그대로 붙인다. 강수량이 직전 1시간 누적이라 한 시간 구간과 맞는다.
처리
- visitor_mean 은 한 시간 안 10분 값의 평균이다. 10분 값이 min_bins 개 미만이면 버린다.
- 0 은 낮에도 그대로 둔다(사람이 안 지나갔을 수 있다).
- congestion 은 visitor_mean / (센서별 분위수), 1 이 넘으면 1 이다. 분위수는 학습 기간
  (train_start ~ train_end)의 행만으로 센서마다 구한다. 구해도 0 인 센서는 정규화할 수
  없어 행을 버리고 보고서에 남긴다.
- 센서의 자치구는 가장 많이 기록된 하나다. 다른 자치구로 기록된 행(자치구가 잘못
  찍힌 주, 센서를 옮기기 전 구간)은 버리고 개수를 보고서에 남긴다.
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


def hour_end(measured_at: np.ndarray) -> np.ndarray:
    """구간 끝 시각 → 그 시각이 속한 한 시간 (H-1:00, H:00] 의 끝 정시 H."""
    minutes_since_epoch = measured_at.astype("datetime64[m]").astype(np.int64)
    minutes_per_hour = 60
    ceil_hours = -(-minutes_since_epoch // minutes_per_hour)
    return ceil_hours.astype("datetime64[h]").astype("datetime64[s]")


def aggregate_hourly(history: pa.Table, min_bins: int) -> tuple[pa.Table, int]:
    """10분 값을 센서·시간별 평균으로 묶는다.

    반환: (열 sensor_code, hour_end, visitor_mean, bins 의 표,
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
            "visitor_mean": (total[keep] / bins[keep]).astype(np.float32),
            "bins": bins[keep],
        }
    )
    return table, int((~keep).sum())


def sensor_scales(
    sensor_code: np.ndarray,
    slot_start: np.ndarray,
    visitor_mean: np.ndarray,
    train_start: str,
    train_end: str,
    quantile: float,
) -> dict[int, float]:
    """센서별 정규화 기준값: 학습 기간(train_end 날짜 포함)의 visitor_mean 분위수."""
    in_train = (slot_start >= np.datetime64(train_start)) & (
        slot_start < np.datetime64(train_end) + np.timedelta64(1, "D")
    )
    codes, values = sensor_code[in_train], visitor_mean[in_train]
    order = np.argsort(codes, kind="stable")
    codes, values = codes[order], values[order]
    unique, starts = np.unique(codes, return_index=True)
    scales = {}
    for code, group in zip(unique, np.split(values, starts[1:])):
        scales[int(code)] = float(np.quantile(group, quantile))
    return scales


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


def build_training_set(
    hourly: pa.Table,
    scales: dict[int, float],
    districts: dict[int, str],
    places: dict[int, tuple[float, float]],
    weather: pa.Table,
    calendar: pa.Table,
) -> pa.Table:
    """센서·시간별 평균에 정규화 값, 센서 정보, 날씨, 달력을 붙인다."""
    codes = hourly["sensor_code"].to_numpy()
    scale = np.array([scales[int(c)] for c in codes])
    mean = hourly["visitor_mean"].to_numpy()
    congestion = np.clip(mean / scale, 0.0, 1.0).astype(np.float32)

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
            "visitor_mean": hourly["visitor_mean"],
            "congestion": congestion,
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
        "visitor_mean",
        "congestion",
    ]
    return table.select(names).sort_by(
        [("sensor_code", "ascending"), ("slot_start", "ascending")]
    )


def count_missing(column: pa.ChunkedArray) -> int:
    """null(조인에서 못 찾음)과 NaN(날씨 원본 결측)의 합."""
    return int(column.null_count + np.isnan(column.fill_null(0.0).to_numpy()).sum())


def make_report(
    table: pa.Table, dropped: dict[str, Any], scales: dict[int, float]
) -> dict[str, Any]:
    visitor = table["visitor_mean"].to_numpy()
    hour_of_day = table["hour_of_day"].to_numpy()
    congestion = table["congestion"].to_numpy()
    zero = visitor == 0
    values = np.array(list(scales.values()))
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
        "congestion_at_one_share": round(float((congestion >= 1).mean()), 4),
        "missing_temp": count_missing(table["temp"]),
        "missing_rain_mm": count_missing(table["rain_mm"]),
        "missing_calendar": int(table["is_holiday"].null_count),
        "scale_min": round(float(values.min()), 3),
        "scale_median": round(float(np.median(values)), 3),
        "scale_max": round(float(values.max()), 3),
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
    scale_path = data_path(config["scale_output"])
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
    hourly, short_hours = aggregate_hourly(history, config["min_bins"])
    ends = hourly["hour_end"].to_numpy()
    in_weather = (ends >= first_hour) & (ends <= last_hour)
    located = np.isin(hourly["sensor_code"].to_numpy(), list(places))
    hourly = hourly.filter(pa.array(in_weather & located))

    scales = sensor_scales(
        hourly["sensor_code"].to_numpy(),
        hourly["hour_end"].to_numpy() - HOUR.astype("timedelta64[s]"),
        hourly["visitor_mean"].to_numpy(),
        config["train_start"],
        config["train_end"],
        config["quantile"],
    )
    zero_scale = sorted(code for code, scale in scales.items() if scale <= 0)
    usable = {code: scale for code, scale in scales.items() if scale > 0}
    no_train_rows = sorted(set(hourly["sensor_code"].to_pylist()) - set(scales))
    hourly = hourly.filter(
        pa.array(np.isin(hourly["sensor_code"].to_numpy(), list(usable)))
    )

    table = build_training_set(hourly, usable, districts, places, weather, calendar)
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, output, compression=PARQUET_COMPRESSION)

    scale_path.write_text(
        json.dumps(
            {
                "quantile": config["quantile"],
                "train_start": config["train_start"],
                "train_end": config["train_end"],
                "scales": {str(code): scale for code, scale in sorted(usable.items())},
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    dropped = {
        "rows_dropped_other_district": rows_other_district,
        "hours_dropped_few_bins": short_hours,
        "sensors_without_location": no_place,
        "sensors_zero_scale": zero_scale,
        "sensors_no_train_rows": no_train_rows,
    }
    report_path.write_text(
        json.dumps(make_report(table, dropped, usable), ensure_ascii=False, indent=1)
        + "\n",
        encoding="utf-8",
    )
    print(
        f"행 {table.num_rows:,}, 센서 {len(usable)}개, "
        f"결측 기온 {count_missing(table['temp']):,} "
        f"강수 {count_missing(table['rain_mm']):,} "
        f"→ {output} ({output.stat().st_size / 1e6:.1f} MB, "
        f"{time.time() - started:.0f}s)",
        flush=True,
    )
    print(f"보고서 {report_path}", flush=True)


if __name__ == "__main__":
    main()
