"""기상청 동네예보로 도착지·도착 시각의 날씨를 구한다.

도착 시각에 따라 쓰는 API가 다르다.
- 현재 시각의 정시: 초단기실황 (관측값)
- 약 6시간 안: 초단기예보
- 그 뒤 약 4일: 단기예보
혼잡도 예측 모델이 시간 단위라서, 요청 시각은 가장 가까운 정시로 맞춘다(30분은 올림).
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import httpx

from app.config import Settings
from core.kma_grid import to_grid

KST = timezone(timedelta(hours=9))
OK_CODE = "00"
# 조건에 맞는 자료가 없을 때 오는 코드. 오류가 아니라 빈 결과로 다룬다.
NO_DATA_CODE = "03"

OBSERVATION_PATH = "/getUltraSrtNcst"
ULTRA_FORECAST_PATH = "/getUltraSrtFcst"
SHORT_FORECAST_PATH = "/getVilageFcst"

# 기상청이 자료를 내는 규칙. 기준 시각에서 이만큼 지나야 받을 수 있다.
OBSERVATION_DELAY = timedelta(minutes=10)
ULTRA_FORECAST_DELAY = timedelta(minutes=45)
SHORT_FORECAST_DELAY = timedelta(minutes=10)
# 초단기예보는 매시 30분에 발표하고, 발표 30분 뒤부터 6시간(정시 6개)을 예보한다.
ULTRA_FORECAST_MINUTE = 30
ULTRA_FORECAST_HOURS = 6
# 단기예보 발표 시각(시)
SHORT_FORECAST_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)

# 자료 종류별 항목: (기온, 강수량, 강수형태)
OBSERVATION_CATEGORIES = ("T1H", "RN1", "PTY")
ULTRA_FORECAST_CATEGORIES = ("T1H", "RN1", "PTY")
SHORT_FORECAST_CATEGORIES = ("TMP", "PCP", "PTY")

NO_RAIN_TEXTS = {"", "0", "-", "강수없음"}
# '1mm 미만'은 값을 알 수 없어 중간쯤으로 둔다.
RAIN_BELOW_ONE_MM = 0.5

Source = Literal["observation", "ultra_short_forecast", "short_forecast"]
Precipitation = Literal["none", "rain", "sleet", "snow", "shower"]
# 강수형태 코드: 실황·초단기예보 0~3,5~7 / 단기예보 0~4
PRECIPITATION_CODES: dict[str, Precipitation] = {
    "0": "none",
    "1": "rain",
    "2": "sleet",
    "3": "snow",
    "4": "shower",
    "5": "rain",
    "6": "sleet",
    "7": "snow",
}


@dataclass(frozen=True)
class Weather:
    source: Source
    time: datetime
    temp_c: float
    rain_mm: float
    precipitation: Precipitation


class WeatherError(Exception):
    """기상청 API 호출이나 응답 해석이 실패했을 때."""


class WeatherRangeError(Exception):
    """요청한 좌표나 시각의 날씨를 구할 수 없을 때(범위 밖)."""


class KeyedTtlCache[K, T]:
    """키마다 값 하나를 ttl_s 초 동안 들고 있는다."""

    def __init__(
        self, ttl_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.ttl_s = ttl_s
        self.clock = clock
        self.entries: dict[K, tuple[float, T]] = {}

    def get(self, key: K) -> T | None:
        entry = self.entries.get(key)
        if entry is None or self.clock() - entry[0] >= self.ttl_s:
            return None
        return entry[1]

    def set(self, key: K, value: T) -> None:
        now = self.clock()
        # 기준 시각이 바뀌면 키도 바뀌어 쌓이기만 하므로, 만료된 것은 치운다.
        self.entries = {
            k: v for k, v in self.entries.items() if now - v[0] < self.ttl_s
        }
        self.entries[key] = (now, value)


ItemCache = KeyedTtlCache[tuple, list[dict[str, Any]]]


def create_kma_client(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    return httpx.Client(
        base_url=settings.kma_base_url,
        params={"authKey": settings.kma_api_key.get_secret_value()},
        timeout=settings.kma_timeout_s,
        transport=transport,
    )


def floor_hour(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def round_to_hour(moment: datetime) -> datetime:
    """가장 가까운 정시. 30분은 올린다."""
    return floor_hour(moment + timedelta(minutes=30))


def observation_base(now: datetime) -> datetime:
    return floor_hour(now - OBSERVATION_DELAY)


def ultra_forecast_base(now: datetime) -> datetime:
    moment = now - ULTRA_FORECAST_DELAY
    if moment.minute < ULTRA_FORECAST_MINUTE:
        moment -= timedelta(hours=1)
    return floor_hour(moment).replace(minute=ULTRA_FORECAST_MINUTE)


def short_forecast_base(now: datetime) -> datetime:
    moment = now - SHORT_FORECAST_DELAY
    hours = [h for h in SHORT_FORECAST_HOURS if h <= moment.hour]
    if hours:
        return floor_hour(moment).replace(hour=hours[-1])
    return floor_hour(moment - timedelta(days=1)).replace(hour=SHORT_FORECAST_HOURS[-1])


def parse_rain_mm(text: str) -> float:
    """강수량 문구를 mm 로. 예: '강수없음', '1mm 미만', '2.0mm', '30.0~50.0mm'."""
    text = text.strip()
    if text in NO_RAIN_TEXTS:
        return 0.0
    if "미만" in text:
        return RAIN_BELOW_ONE_MM
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)][:2]
    if not numbers:
        raise ValueError(text)
    # 범위는 가운데 값, '이상'은 그 값을 쓴다.
    return sum(numbers) / len(numbers)


def request_items(
    client: httpx.Client,
    path: str,
    base: datetime,
    grid: tuple[int, int],
    page_size: int,
    cache: ItemCache,
) -> list[dict[str, Any]]:
    """한 기준 시각·격자의 전체 행. 캐시가 살아 있으면 API를 부르지 않는다."""
    key = (path, grid, base)
    cached = cache.get(key)
    if cached is not None:
        return cached
    items: list[dict[str, Any]] = []
    page = 1
    try:
        while True:
            response = client.get(
                path,
                params={
                    "pageNo": page,
                    "numOfRows": page_size,
                    "dataType": "JSON",
                    "base_date": base.strftime("%Y%m%d"),
                    "base_time": base.strftime("%H%M"),
                    "nx": grid[0],
                    "ny": grid[1],
                },
            )
            response.raise_for_status()
            body = response.json()["response"]
            code = body["header"]["resultCode"]
            if code == NO_DATA_CODE:
                break
            if code != OK_CODE:
                raise WeatherError(code)
            page_items = body["body"]["items"]["item"]
            items += page_items
            if not page_items or len(items) >= int(body["body"]["totalCount"]):
                break
            page += 1
    except WeatherError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        # 요청 주소에 API 키가 들어 있어서 원인 예외(주소 포함)를 잇지 않는다.
        raise WeatherError from None
    cache.set(key, items)
    return items


def to_weather(
    source: Source,
    hour: datetime,
    values: dict[str, str],
    categories: tuple[str, str, str],
) -> Weather:
    temp_key, rain_key, type_key = categories
    try:
        return Weather(
            source=source,
            time=hour,
            temp_c=float(values[temp_key]),
            rain_mm=parse_rain_mm(values[rain_key]),
            precipitation=PRECIPITATION_CODES[values[type_key]],
        )
    except (KeyError, ValueError):
        raise WeatherError from None


def forecast_values(
    items: list[dict[str, Any]], hour: datetime
) -> dict[str, str] | None:
    """예보 행 중 hour 정시의 항목별 값. 그 시각 행이 없으면 None."""
    date, clock = hour.strftime("%Y%m%d"), hour.strftime("%H%M")
    values = {
        item["category"]: item["fcstValue"]
        for item in items
        if item["fcstDate"] == date and item["fcstTime"] == clock
    }
    return values or None


def read_weather(
    client: httpx.Client,
    lat: float,
    lon: float,
    at: datetime,
    settings: Settings,
    cache: ItemCache,
    now: datetime | None = None,
) -> Weather:
    """위경도(lat, lon)의 at 시각 날씨. at 은 가까운 정시로 맞춘다.

    WeatherRangeError: 격자 밖 좌표, 이미 지난 시각, 예보가 닿지 않는 먼 시각
    WeatherError: 기상청 호출·응답 실패
    """
    now = (now or datetime.now(KST)).astimezone(KST)
    try:
        grid = to_grid(lat, lon)
    except ValueError as error:
        raise WeatherRangeError("예보를 제공하지 않는 위치입니다.") from error
    target = round_to_hour(at.astimezone(KST))
    page_size = settings.kma_page_size

    observed = observation_base(now)
    if target < observed:
        raise WeatherRangeError("지난 시각의 날씨는 제공하지 않습니다.")
    if target == observed:
        items = request_items(
            client, OBSERVATION_PATH, observed, grid, page_size, cache
        )
        values = {item["category"]: item["obsrValue"] for item in items}
        return to_weather("observation", target, values, OBSERVATION_CATEGORIES)

    ultra_base = ultra_forecast_base(now)
    ultra_first = ultra_base + timedelta(minutes=ULTRA_FORECAST_MINUTE)
    ultra_last = ultra_first + timedelta(hours=ULTRA_FORECAST_HOURS - 1)
    if ultra_first <= target <= ultra_last:
        items = request_items(
            client, ULTRA_FORECAST_PATH, ultra_base, grid, page_size, cache
        )
        values = forecast_values(items, target)
        if values is None:
            raise WeatherError
        return to_weather(
            "ultra_short_forecast", target, values, ULTRA_FORECAST_CATEGORIES
        )

    items = request_items(
        client, SHORT_FORECAST_PATH, short_forecast_base(now), grid, page_size, cache
    )
    values = forecast_values(items, target)
    if values is None:
        if items:
            raise WeatherRangeError("예보가 닿지 않는 시각입니다.")
        raise WeatherError
    return to_weather("short_forecast", target, values, SHORT_FORECAST_CATEGORIES)
