"""기상청 AWS 시간자료를 자치구·시간 단위 hourly.parquet 한 파일로 정리한다.

실행: pipeline/ 에서 uv run python steps/11_build_weather.py
- 입력: raw/weather/aws/OBS_AWS_TIM_*.csv (지점, 일시, 기온, 강수량)
        raw/weather/aws_stations.csv (지점 위치. 종료일이 빈 행이 현재 위치)
        interim/sdot/history.parquet (혼잡도 쪽 자치구 이름·센서 코드)
        data/processed/sdot_sensors.json (센서 위치)
- 출력: interim/weather/hourly.parquet 과 hourly_report.json
  열: district, hour, temp, rain_mm
  district 는 혼잡도 history 의 자치구 이름(영문)과 같아서 (district, hour)로 붙는다.
  hour 는 원본 일시를 그대로 둔 정시다. 강수량이 직전 1시간 누적인지는 원본 설명을
  따르며, 혼잡도 시각과 맞추는 일은 모델 단계에서 정한다.
처리
- 인코딩은 파일마다 감지한다(cp949 또는 UTF-8).
- 자치구의 값은 그 구에 있는 AWS 지점들의 평균이다. 지점이 없는 구(종로구)와 구가 아닌
  지역(서울대공원)은 센서 위치 중심에서 가장 가까운 지점 하나를 쓴다.
- 빈 값은 비워 둔다. 0 으로 채우면 비가 안 온 것과 구분되지 않는다.
- 결측은 가까운 자치구 값으로 먼저 채우고, 남은 기온의 짧은 구간은 앞뒤 값으로 잇는다.
  강수량은 시간으로 이을 수 없어서 남기고 보고서에 센다.
- (지점, 일시)가 같은 행은 하나만 남긴다. 값이 다르면 보고서에 개수를 남기고 뒤에 읽은
  값을 쓴다.
그래프(00~04 단계)와 관계가 없어서 run_all.py 에 넣지 않고 따로 실행한다.
"""

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from common import CONFIG_PATH, data_path, load_config, repo_path, require_files

STATION_COLUMN = "지점"
TIME_COLUMN = "일시"
TEMP_PREFIX = "기온"
RAIN_PREFIX = "강수량"
END_DATE_COLUMN = "종료일"
START_DATE_COLUMN = "시작일"
ADDRESS_COLUMN = "지점주소"
LAT_COLUMN = "위도"
LON_COLUMN = "경도"
TIME_FORMAT = "%Y-%m-%d %H:%M"
DISTRICT_PATTERN = re.compile(r"(\S+구)(?:\s|$)")
SECONDS_PER_HOUR = 3600
EARTH_RADIUS_KM = 6371.0
PARQUET_COMPRESSION = "zstd"


@dataclass
class Station:
    code: int
    lat: float
    lon: float
    # 지점주소의 자치구(한글). 주소에서 못 찾으면 None
    district: str | None


@dataclass
class Observations:
    """파일들을 합친 관측. 키는 (지점, 정시)이고 값은 (기온, 강수량), 빈 값은 None."""

    values: dict[tuple[int, datetime], tuple[float | None, float | None]]
    bad_rows: dict[str, int]
    rows: dict[str, int]
    duplicates_removed: int = 0
    conflicting_duplicates: int = 0


def detect_encoding(raw: bytes) -> str:
    """UTF-8 로 읽히면 UTF-8, 아니면 cp949."""
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return "cp949"
    return "utf-8-sig"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    # 지점 목록 파일은 첫 줄이 비어 있어서 빈 줄은 건너뛴다.
    lines = [
        line for line in raw.decode(detect_encoding(raw)).splitlines() if line.strip()
    ]
    return list(csv.DictReader(lines))


def parse_number(text: str) -> float | None:
    text = text.strip()
    return float(text) if text else None


def read_stations(path: Path) -> dict[int, Station]:
    """지점마다 종료일이 빈(현재) 행의 위치. 현재 행이 여럿이면 시작일이 늦은 행."""
    current: dict[int, dict[str, str]] = {}
    for row in read_csv_rows(path):
        if row[END_DATE_COLUMN].strip():
            continue
        code = int(row[STATION_COLUMN])
        known = current.get(code)
        if known is None or row[START_DATE_COLUMN] > known[START_DATE_COLUMN]:
            current[code] = row
    stations = {}
    for code, row in current.items():
        match = DISTRICT_PATTERN.search(row[ADDRESS_COLUMN].replace("서울특별시", ""))
        stations[code] = Station(
            code=code,
            lat=float(row[LAT_COLUMN]),
            lon=float(row[LON_COLUMN]),
            district=match[1] if match else None,
        )
    return stations


def read_observations(paths: list[Path]) -> Observations:
    result = Observations(values={}, bad_rows={}, rows={})
    for path in paths:
        rows = read_csv_rows(path)
        header = rows[0].keys() if rows else []
        temp_key = next((k for k in header if k.startswith(TEMP_PREFIX)), None)
        rain_key = next((k for k in header if k.startswith(RAIN_PREFIX)), None)
        if temp_key is None or rain_key is None:
            raise SystemExit(f"기온·강수량 열을 찾지 못했습니다: {path.name}")
        bad = 0
        for row in rows:
            try:
                code = int(row[STATION_COLUMN])
                hour = datetime.strptime(row[TIME_COLUMN], TIME_FORMAT)
                if hour.minute:
                    raise ValueError("정시가 아님")
                value = (parse_number(row[temp_key]), parse_number(row[rain_key]))
            except (ValueError, KeyError, TypeError):
                bad += 1
                continue
            known = result.values.get((code, hour))
            if known is not None:
                result.duplicates_removed += 1
                result.conflicting_duplicates += known != value
            result.values[(code, hour)] = value
        result.rows[path.name] = len(rows)
        if bad:
            result.bad_rows[path.name] = bad
    return result


def haversine_km(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (
        np.sin((p2 - p1) / 2) ** 2
        + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def station_grid(
    observations: Observations, codes: list[int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """지점×시간 격자. 반환: (정시 목록, 기온, 강수량). 관측이 없는 칸은 NaN."""
    hours = [hour for _, hour in observations.values]
    start = min(hours)
    count = int((max(hours) - start).total_seconds() // SECONDS_PER_HOUR) + 1
    index = {code: i for i, code in enumerate(codes)}
    temp = np.full((len(codes), count), np.nan)
    rain = np.full((len(codes), count), np.nan)
    for (code, hour), (t, r) in observations.values.items():
        if code not in index:
            continue
        column = int((hour - start).total_seconds() // SECONDS_PER_HOUR)
        if t is not None:
            temp[index[code], column] = t
        if r is not None:
            rain[index[code], column] = r
    start64 = np.datetime64(start, "s")
    grid_hours = start64 + np.arange(count) * np.timedelta64(SECONDS_PER_HOUR, "s")
    return grid_hours, temp, rain


def mean_ignoring_nan(values: np.ndarray) -> np.ndarray:
    """행(지점)들의 평균. 전부 NaN 인 시간은 NaN."""
    count = (~np.isnan(values)).sum(axis=0)
    total = np.nansum(values, axis=0)
    return np.where(count > 0, total / np.maximum(count, 1), np.nan)


def fill_from_neighbors(
    values: np.ndarray, order: list[list[int]], neighbors: int
) -> np.ndarray:
    """NaN 칸을 같은 시간에 값이 있는 가까운 자치구 neighbors 개의 평균으로 채운다."""
    filled = values.copy()
    for district, near in enumerate(order):
        missing = np.isnan(values[district])
        if not missing.any():
            continue
        total = np.zeros(values.shape[1])
        count = np.zeros(values.shape[1])
        for other in near:
            usable = missing & ~np.isnan(values[other]) & (count < neighbors)
            total[usable] += values[other][usable]
            count[usable] += 1
        found = count > 0
        filled[district, found] = total[found] / count[found]
    return filled


def fill_short_gaps(row: np.ndarray, max_gap: int) -> np.ndarray:
    """앞뒤 값이 있는 max_gap 시간 이하의 NaN 구간을 직선으로 잇는다."""
    out = row.copy()
    missing = np.flatnonzero(np.isnan(out))
    if missing.size == 0:
        return out
    for run in np.split(missing, np.flatnonzero(np.diff(missing) > 1) + 1):
        start, end = run[0], run[-1] + 1
        if start > 0 and end < len(out) and len(run) <= max_gap:
            out[start:end] = np.interp(
                run, [start - 1, end], [out[start - 1], out[end]]
            )
    return out


def read_district_sensors(history_path: Path) -> dict[str, list[int]]:
    """혼잡도 history 의 자치구별 센서 코드."""
    table = pq.read_table(history_path, columns=["sensor_code", "district"])
    pairs = table.group_by(["sensor_code", "district"]).aggregate([])
    sensors: dict[str, list[int]] = {}
    for code, district in zip(
        pairs["sensor_code"].to_pylist(), pairs["district"].to_pylist()
    ):
        if district:
            sensors.setdefault(district, []).append(code)
    return {name: sorted(codes) for name, codes in sorted(sensors.items())}


def district_centers(
    district_sensors: dict[str, list[int]],
    sensor_places: dict[int, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """자치구별 센서 위치의 평균(위도, 경도)."""
    centers = {}
    for name, codes in district_sensors.items():
        places = [sensor_places[code] for code in codes if code in sensor_places]
        if not places:
            raise SystemExit(f"센서 위치를 아는 센서가 없는 자치구입니다: {name}")
        centers[name] = (
            float(np.mean([p[0] for p in places])),
            float(np.mean([p[1] for p in places])),
        )
    return centers


def assign_stations(
    names: list[str],
    korean_names: dict[str, str | None],
    stations: dict[int, Station],
    centers: dict[str, tuple[float, float]],
) -> tuple[dict[str, list[int]], dict[str, float]]:
    """자치구마다 쓸 지점. 같은 구 지점이 없으면 센서 중심에서 가장 가까운 지점 하나.

    반환: (자치구 → 지점 코드, 가까운 지점으로 대체한 자치구 → 거리 km)
    """
    assigned: dict[str, list[int]] = {}
    nearest_km: dict[str, float] = {}
    codes = np.array(list(stations))
    lats = np.array([stations[c].lat for c in codes])
    lons = np.array([stations[c].lon for c in codes])
    for name in names:
        korean = korean_names[name]
        own = [c for c in stations if korean and stations[c].district == korean]
        if own:
            assigned[name] = sorted(own)
            continue
        lat, lon = centers[name]
        distance = haversine_km(np.array(lat), np.array(lon), lats, lons)
        closest = int(np.argmin(distance))
        assigned[name] = [int(codes[closest])]
        nearest_km[name] = round(float(distance[closest]), 2)
    return assigned, nearest_km


def build_hourly(
    observations: Observations,
    assigned: dict[str, list[int]],
    centers: dict[str, tuple[float, float]],
    neighbors: int,
    max_gap_hours: int,
) -> tuple[pa.Table, dict]:
    """자치구×시간 표와 결측 보고."""
    names = list(assigned)
    codes = sorted({c for stations in assigned.values() for c in stations})
    hours, temp_grid, rain_grid = station_grid(observations, codes)
    row_of = {code: i for i, code in enumerate(codes)}

    def by_district(grid: np.ndarray) -> np.ndarray:
        return np.stack(
            [
                mean_ignoring_nan(grid[[row_of[c] for c in assigned[name]]])
                for name in names
            ]
        )

    temp, rain = by_district(temp_grid), by_district(rain_grid)
    missing_before = {
        "temp": int(np.isnan(temp).sum()),
        "rain_mm": int(np.isnan(rain).sum()),
    }

    lat = np.array([centers[n][0] for n in names])
    lon = np.array([centers[n][1] for n in names])
    distance = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    order = [
        [int(j) for j in np.argsort(distance[i]) if j != i] for i in range(len(names))
    ]
    temp = fill_from_neighbors(temp, order, neighbors)
    rain = fill_from_neighbors(rain, order, neighbors)
    missing_after_neighbors = int(np.isnan(temp).sum())
    temp = np.stack([fill_short_gaps(row, max_gap_hours) for row in temp])

    count = len(hours)
    table = pa.table(
        {
            "district": pa.array(np.repeat(names, count), type=pa.string()),
            "hour": pa.array(np.tile(hours, len(names)), type=pa.timestamp("s")),
            "temp": pa.array(temp.reshape(-1), type=pa.float32()),
            "rain_mm": pa.array(rain.reshape(-1), type=pa.float32()),
        }
    ).sort_by([("hour", "ascending"), ("district", "ascending")])
    stats = {
        "hours": count,
        "missing_before_fill": missing_before,
        "temp_missing_after_neighbors": missing_after_neighbors,
        "missing_after_fill": {
            "temp": int(np.isnan(temp).sum()),
            "rain_mm": int(np.isnan(rain).sum()),
        },
    }
    return table, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["weather"]
    source = data_path(config["source_dir"])
    stations_path = data_path(config["stations"])
    history_path = data_path(config["history"])
    sensors_path = repo_path(config["sensors"])
    output = data_path(config["output"])
    report_path = data_path(config["report"])
    require_files(source, stations_path, history_path, sensors_path)

    started = time.time()
    files = sorted(source.glob(config["file_pattern"]))
    if not files:
        raise SystemExit(f"AWS 시간자료({config['file_pattern']})가 없습니다: {source}")
    stations = read_stations(stations_path)
    observations = read_observations(files)

    district_sensors = read_district_sensors(history_path)
    korean_names = config["districts"]
    unknown = sorted(set(district_sensors) - set(korean_names))
    if unknown:
        raise SystemExit(
            f"config.yaml weather.districts 에 없는 자치구입니다: {unknown}"
        )
    sensor_places = {
        sensor["code"]: (sensor["lat"], sensor["lon"])
        for sensor in json.loads(sensors_path.read_text(encoding="utf-8"))["sensors"]
    }
    centers = district_centers(district_sensors, sensor_places)
    observed = {code for code, _ in observations.values}
    usable = {code: s for code, s in stations.items() if code in observed}
    assigned, nearest_km = assign_stations(
        list(district_sensors), korean_names, usable, centers
    )

    table, stats = build_hourly(
        observations,
        assigned,
        centers,
        config["fill_neighbors"],
        config["max_gap_hours"],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, output, compression=PARQUET_COMPRESSION)

    report = {
        "files": observations.rows,
        "bad_rows": observations.bad_rows,
        "duplicates_removed": observations.duplicates_removed,
        "conflicting_duplicates": observations.conflicting_duplicates,
        "stations_in_data": len(observed),
        "stations_without_location": sorted(observed - set(stations)),
        "rows": table.num_rows,
        "districts": len(assigned),
        "first_hour": table["hour"][0].as_py().isoformat(),
        "last_hour": table["hour"][-1].as_py().isoformat(),
        "stations_by_district": assigned,
        "nearest_station_km": nearest_km,
        **stats,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"행 {table.num_rows:,}, 자치구 {len(assigned)}개, 지점 {len(observed)}개, "
        f"결측(채운 뒤) 기온 {stats['missing_after_fill']['temp']:,} "
        f"강수 {stats['missing_after_fill']['rain_mm']:,} "
        f"→ {output} ({output.stat().st_size / 1e6:.1f} MB, "
        f"{time.time() - started:.0f}s)",
        flush=True,
    )
    print(f"보고서 {report_path}", flush=True)


if __name__ == "__main__":
    main()
