"""자치구별 날씨를 weather_now(실황), weather_daily(하루치 예보)에 쌓는다.

자치구 위치는 그 구 센서 위치의 평균이다(pipeline 11 단계와 같은 방식). 센서의 자치구는
sdot_readings 에 쌓인 값을 쓰므로 유동인구를 먼저 수집해야 한다.
"""

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collector.models import SdotReading, WeatherDaily, WeatherNow
from app.collector.store import as_kst, insert_new
from app.config import Settings
from app.repositories.sensor_repository import Sensor
from app.services.weather_service import (
    OBSERVATION_PATH,
    PRECIPITATION_CODES,
    SHORT_FORECAST_DELAY,
    SHORT_FORECAST_PATH,
    ItemCache,
    floor_hour,
    observation_base,
    parse_rain_mm,
    request_items,
)
from core.kma_grid import to_grid

Grid = tuple[int, int]


def district_grids(
    session: Session, sensors: Mapping[int, Sensor], since: datetime
) -> dict[str, Grid]:
    """since 뒤에 수집한 센서·자치구 짝으로 자치구마다 격자(nx, ny)를 구한다."""
    pairs = session.execute(
        select(SdotReading.sensor_code, SdotReading.district)
        .where(SdotReading.measured_at >= since, SdotReading.district.is_not(None))
        .distinct()
    )
    positions: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for code, district in pairs:
        if code in sensors:
            positions[district].append(sensors[code].position)
    grids: dict[str, Grid] = {}
    for district, points in sorted(positions.items()):
        lon = sum(point[0] for point in points) / len(points)
        lat = sum(point[1] for point in points) / len(points)
        try:
            grids[district] = to_grid(lat, lon)
        except ValueError:
            continue
    return grids


def number(values: Mapping[str, str], key: str) -> float | None:
    try:
        return float(values[key])
    except (KeyError, ValueError):
        return None


def rain(values: Mapping[str, str], key: str) -> float | None:
    try:
        return parse_rain_mm(values[key])
    except (KeyError, ValueError):
        return None


def whole(values: Mapping[str, str], key: str) -> int | None:
    value = number(values, key)
    return None if value is None else round(value)


def collect_weather_now(
    session: Session,
    client: httpx.Client,
    grids: Mapping[str, Grid],
    settings: Settings,
    now: datetime,
    cache: ItemCache,
) -> int:
    """지난 collector_backfill_hours 정시 중 DB에 없는 실황만 받는다.

    새로 넣은 행 수.
    """
    latest = observation_base(now)
    hours = [
        latest - timedelta(hours=h) for h in range(settings.collector_backfill_hours)
    ]
    stored = {
        (district, as_kst(observed))
        for district, observed in session.execute(
            select(WeatherNow.district, WeatherNow.observed_at).where(
                WeatherNow.observed_at >= hours[-1]
            )
        )
    }
    rows: list[dict[str, Any]] = []
    for district, grid in grids.items():
        for hour in hours:
            if (district, hour) in stored:
                continue
            items = request_items(
                client, OBSERVATION_PATH, hour, grid, settings.kma_page_size, cache
            )
            if not items:
                continue
            values = {item["category"]: item["obsrValue"] for item in items}
            rows.append(
                {
                    "district": district,
                    "observed_at": hour,
                    "nx": grid[0],
                    "ny": grid[1],
                    "temp_c": number(values, "T1H"),
                    "rain_mm": rain(values, "RN1"),
                    "precipitation": PRECIPITATION_CODES.get(values.get("PTY", "")),
                    "humidity": number(values, "REH"),
                    "wind_ms": number(values, "WSD"),
                    "collected_at": now,
                }
            )
    return insert_new(session, WeatherNow, rows)


def daily_issue(now: datetime, issue_hour: int) -> datetime:
    """받을 수 있는 가장 최근 issue_hour 시 단기예보 발표 시각."""
    ready = now - SHORT_FORECAST_DELAY
    issue = floor_hour(ready).replace(hour=issue_hour)
    return issue if issue <= ready else issue - timedelta(days=1)


def forecast_rows(
    items: list[dict[str, Any]],
    district: str,
    grid: Grid,
    issued: datetime,
    hours: int,
    now: datetime,
) -> list[dict[str, Any]]:
    """발표 뒤 hours 시간 안의 정시별 예보 행."""
    by_hour: dict[datetime, dict[str, str]] = defaultdict(dict)
    for item in items:
        moment = datetime.strptime(
            item["fcstDate"] + item["fcstTime"], "%Y%m%d%H%M"
        ).replace(tzinfo=issued.tzinfo)
        if issued < moment <= issued + timedelta(hours=hours):
            by_hour[moment][item["category"]] = item["fcstValue"]
    return [
        {
            "district": district,
            "issued_at": issued,
            "forecast_at": moment,
            "nx": grid[0],
            "ny": grid[1],
            "temp_c": number(values, "TMP"),
            "rain_mm": rain(values, "PCP"),
            "rain_prob": whole(values, "POP"),
            "precipitation": PRECIPITATION_CODES.get(values.get("PTY", "")),
            "sky": whole(values, "SKY"),
            "humidity": number(values, "REH"),
            "wind_ms": number(values, "WSD"),
            "collected_at": now,
        }
        for moment, values in sorted(by_hour.items())
    ]


def collect_weather_daily(
    session: Session,
    client: httpx.Client,
    grids: Mapping[str, Grid],
    settings: Settings,
    now: datetime,
    cache: ItemCache,
) -> int:
    """가장 최근 하루치 예보 중 DB에 없는 자치구만 받는다. 새로 넣은 행 수."""
    issued = daily_issue(now, settings.collector_daily_issue_hour)
    stored = set(
        session.scalars(
            select(WeatherDaily.district)
            .where(WeatherDaily.issued_at == issued)
            .distinct()
        )
    )
    rows: list[dict[str, Any]] = []
    for district, grid in grids.items():
        if district in stored:
            continue
        items = request_items(
            client, SHORT_FORECAST_PATH, issued, grid, settings.kma_page_size, cache
        )
        rows += forecast_rows(
            items, district, grid, issued, settings.collector_daily_hours, now
        )
    return insert_new(session, WeatherDaily, rows)
