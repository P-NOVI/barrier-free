from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_kma_client, get_weather_cache
from app.main import app
from app.routers import weather as weather_router
from app.services import weather_service as service
from app.services.weather_service import (
    KST,
    ItemCache,
    KeyedTtlCache,
    WeatherError,
    WeatherRangeError,
    create_kma_client,
    read_weather,
)

client = TestClient(app)

Handler = Callable[[httpx.Request], httpx.Response]

SEOUL = (37.5665, 126.9780)
# 기준 시각: 실황 19시, 초단기예보 18:30(19~24시), 단기예보 17시(18시~)
NOW = datetime(2026, 11, 3, 20, 4, tzinfo=KST)
# 실황 20시가 나오는 시각
NOW_OBSERVED = datetime(2026, 11, 3, 20, 14, tzinfo=KST)


def envelope(items: list[dict], total: int | None = None, page: int = 1) -> dict:
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
            "body": {
                "dataType": "JSON",
                "items": {"item": items},
                "pageNo": page,
                "totalCount": len(items) if total is None else total,
            },
        }
    }


def observation(t1h: str = "13.5", rn1: str = "0", pty: str = "0") -> list[dict]:
    values = {"T1H": t1h, "RN1": rn1, "PTY": pty, "REH": "66"}
    return [
        {"baseDate": "20261103", "baseTime": "2000", "category": c, "obsrValue": v}
        for c, v in values.items()
    ]


def forecast(date: str, time: str, **values: str) -> list[dict]:
    return [
        {"fcstDate": date, "fcstTime": time, "category": c, "fcstValue": v}
        for c, v in values.items()
    ]


ULTRA_ITEMS = forecast("20261103", "2100", T1H="12", RN1="강수없음", PTY="0", SKY="1")
SHORT_ITEMS = [
    *forecast("20261104", "1500", TMP="18", PCP="2.0mm", PTY="1", POP="60"),
    *forecast("20261104", "1600", TMP="17", PCP="1mm 미만", PTY="1", POP="60"),
]


def serve(**by_path: list[dict]) -> Handler:
    """경로(getUltraSrtNcst 등)마다 행을 쪽 나눠 돌려준다."""

    def handler(request: httpx.Request) -> httpx.Response:
        items = by_path[request.url.path.rsplit("/", 1)[-1]]
        page = int(request.url.params["pageNo"])
        size = int(request.url.params["numOfRows"])
        part = items[(page - 1) * size : page * size]
        return httpx.Response(200, json=envelope(part, len(items), page))

    return handler


def respond_with_code(code: str) -> Handler:
    body = {"response": {"header": {"resultCode": code, "resultMsg": "메시지"}}}
    return lambda _: httpx.Response(200, json=body)


def time_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("시간 초과", request=request)


@pytest.fixture
def kma() -> Iterator[Callable[[Handler], list[httpx.Request]]]:
    """기상청 API 대신 handler 가 응답하게 하고, 받은 요청 목록을 돌려준다."""

    def use(handler: Handler, now: datetime = NOW) -> list[httpx.Request]:
        clock[0] = now
        received: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            received.append(request)
            return handler(request)

        settings = Settings(_env_file=None, kma_api_key="test-key")

        def override() -> Iterator[httpx.Client]:
            with create_kma_client(settings, httpx.MockTransport(record)) as mock:
                yield mock

        app.dependency_overrides[get_kma_client] = override
        app.dependency_overrides[get_weather_cache] = lambda: cache
        return received

    cache: ItemCache = KeyedTtlCache(600.0)
    clock = [NOW]
    original = weather_router.read_weather
    # 서버 시계를 고정해 기준 시각이 바뀌지 않게 한다.
    weather_router.read_weather = lambda *args: original(*args, now=clock[0])
    yield use
    weather_router.read_weather = original
    app.dependency_overrides.clear()


def get(at: datetime | str | None = None, lat: float = SEOUL[0], lon: float = SEOUL[1]):
    params: dict[str, Any] = {"lat": lat, "lon": lon}
    if at is not None:
        params["at"] = at.isoformat() if isinstance(at, datetime) else at
    return client.get("/api/weather", params=params)


# --- 기준 시각 규칙 ---


@pytest.mark.parametrize(
    ("now", "observed", "ultra", "short"),
    [
        ((20, 4), (19, 0), (18, 30), (17, 0)),
        ((20, 14), (20, 0), (18, 30), (20, 0)),
        ((20, 44), (20, 0), (19, 30), (20, 0)),
        ((20, 46), (20, 0), (19, 30), (20, 0)),
        ((1, 5), (0, 0), (23, 30), (23, 0)),
    ],
)
def test_base_times(now, observed, ultra, short) -> None:
    moment = datetime(2026, 11, 3, *now, tzinfo=KST)

    def hm(base: datetime) -> tuple[int, int]:
        return base.hour, base.minute

    assert hm(service.observation_base(moment)) == observed
    assert hm(service.ultra_forecast_base(moment)) == ultra
    assert hm(service.short_forecast_base(moment)) == short


def test_early_morning_uses_yesterdays_short_forecast() -> None:
    base = service.short_forecast_base(datetime(2026, 11, 3, 1, 5, tzinfo=KST))

    assert base == datetime(2026, 11, 2, 23, 0, tzinfo=KST)


@pytest.mark.parametrize(
    ("text", "mm"),
    [
        ("강수없음", 0.0),
        ("0", 0.0),
        ("1mm 미만", 0.5),
        ("2.0mm", 2.0),
        ("1.0", 1.0),
        ("30.0~50.0mm", 40.0),
        ("50.0mm 이상", 50.0),
    ],
)
def test_parse_rain_mm(text: str, mm: float) -> None:
    assert service.parse_rain_mm(text) == mm


def test_round_to_hour_rounds_half_up() -> None:
    assert service.round_to_hour(datetime(2026, 11, 3, 20, 29, tzinfo=KST)).hour == 20
    assert service.round_to_hour(datetime(2026, 11, 3, 20, 30, tzinfo=KST)).hour == 21


# --- API ---


def test_current_hour_is_observation(kma) -> None:
    received = kma(
        serve(getUltraSrtNcst=observation("13.5", "1.0", "1")), now=NOW_OBSERVED
    )

    response = get(NOW_OBSERVED)

    assert response.status_code == 200
    assert response.json() == {
        "source": "observation",
        "time": "2026-11-03T20:00:00+09:00",
        "temp_c": 13.5,
        "rain_mm": 1.0,
        "precipitation": "rain",
    }
    request = received[0]
    assert request.url.path.endswith("/getUltraSrtNcst")
    assert request.url.params["base_date"] == "20261103"
    assert request.url.params["base_time"] == "2000"
    assert (request.url.params["nx"], request.url.params["ny"]) == ("60", "127")
    assert request.url.params["authKey"] == "test-key"
    assert request.url.params["dataType"] == "JSON"


def test_arrival_in_30_minutes_uses_ultra_short_forecast(kma) -> None:
    received = kma(serve(getUltraSrtFcst=ULTRA_ITEMS))

    # 20:04 + 56분 = 21:00
    response = get(NOW + timedelta(minutes=56))

    assert response.status_code == 200
    assert response.json() == {
        "source": "ultra_short_forecast",
        "time": "2026-11-03T21:00:00+09:00",
        "temp_c": 12.0,
        "rain_mm": 0.0,
        "precipitation": "none",
    }
    assert received[0].url.params["base_time"] == "1830"


def test_far_arrival_uses_short_forecast_and_text_rain(kma) -> None:
    received = kma(serve(getVilageFcst=SHORT_ITEMS))

    response = get(datetime(2026, 11, 4, 15, 20, tzinfo=KST))

    assert response.status_code == 200
    assert response.json() == {
        "source": "short_forecast",
        "time": "2026-11-04T15:00:00+09:00",
        "temp_c": 18.0,
        "rain_mm": 2.0,
        "precipitation": "rain",
    }
    assert received[0].url.params["base_time"] == "1700"


def test_naive_time_is_korean_time(kma) -> None:
    kma(serve(getVilageFcst=SHORT_ITEMS))

    response = get("2026-11-04T15:00:00")

    assert response.status_code == 200
    assert response.json()["time"] == "2026-11-04T15:00:00+09:00"


def test_default_time_is_now(kma) -> None:
    kma(serve(getUltraSrtFcst=forecast("20261103", "2000", T1H="9", RN1="0", PTY="0")))

    response = get()

    assert response.status_code == 200
    assert response.json()["source"] == "ultra_short_forecast"
    assert response.json()["time"] == "2026-11-03T20:00:00+09:00"


def test_cache_avoids_second_call(kma) -> None:
    received = kma(serve(getUltraSrtFcst=ULTRA_ITEMS))

    get(NOW + timedelta(minutes=56))
    second = get(NOW + timedelta(minutes=56))

    assert second.status_code == 200
    assert len(received) == 1


def test_past_time_is_422(kma) -> None:
    kma(serve())

    response = get(NOW - timedelta(hours=3))

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "weather_out_of_range"


def test_time_beyond_forecast_is_422(kma) -> None:
    kma(serve(getVilageFcst=SHORT_ITEMS))

    response = get(NOW + timedelta(days=9))

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "weather_out_of_range"


def test_outside_korea_is_422(kma) -> None:
    received = kma(serve())

    response = get(lat=35.68, lon=139.69)

    assert response.status_code == 422
    assert received == []


@pytest.mark.parametrize(
    "handler",
    [
        respond_with_code("30"),
        respond_with_code("99"),
        lambda _: httpx.Response(500),
        lambda _: httpx.Response(403, json={"result": {"status": 403}}),
        lambda _: httpx.Response(200, text="<html>점검 중</html>"),
        time_out,
        # 필요한 항목이 빠진 응답
        lambda _: httpx.Response(
            200, json=envelope(forecast("20261103", "2100", T1H="12"))
        ),
        # 해당 시각 행이 없는 응답
        respond_with_code("03"),
    ],
)
def test_upstream_failure_is_502_without_key(kma, handler) -> None:
    kma(handler)

    response = get(NOW + timedelta(minutes=56))

    assert response.status_code == 502
    assert response.json()["detail"]["reason"] == "weather_failed"
    assert "test-key" not in response.text


def test_failure_is_not_cached(kma) -> None:
    received = kma(respond_with_code("99"))

    get(NOW + timedelta(minutes=56))
    get(NOW + timedelta(minutes=56))

    assert len(received) == 2


def test_missing_key_is_503() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, kma_api_key=""
    )
    try:
        response = get()
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "weather_unavailable"


def test_invalid_coordinates_are_422() -> None:
    assert (
        client.get("/api/weather", params={"lat": 100, "lon": 127}).status_code == 422
    )


# --- 서비스 ---


def test_short_forecast_is_read_page_by_page() -> None:
    items = [
        row
        for hour in range(1, 6)
        for row in forecast(
            "20261104", f"{hour:02d}00", TMP=str(hour), PCP="강수없음", PTY="0"
        )
    ]
    received: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return serve(getVilageFcst=items)(request)

    settings = Settings(_env_file=None, kma_api_key="test-key", kma_page_size=4)
    with create_kma_client(settings, httpx.MockTransport(record)) as mock:
        weather = read_weather(
            mock,
            *SEOUL,
            datetime(2026, 11, 4, 5, 0, tzinfo=KST),
            settings,
            KeyedTtlCache(600.0),
            now=NOW,
        )

    # 3개 항목 x 5시간 = 15행을 4행씩 4쪽으로 받는다.
    assert len(received) == 4
    assert weather.temp_c == 5.0


def test_range_and_upstream_errors_are_different_types() -> None:
    settings = Settings(_env_file=None, kma_api_key="test-key")
    cache: ItemCache = KeyedTtlCache(600.0)
    with create_kma_client(
        settings, httpx.MockTransport(respond_with_code("99"))
    ) as mock:
        with pytest.raises(WeatherRangeError):
            read_weather(
                mock, *SEOUL, NOW - timedelta(days=1), settings, cache, now=NOW
            )
        with pytest.raises(WeatherError):
            read_weather(
                mock, *SEOUL, NOW + timedelta(hours=1), settings, cache, now=NOW
            )


def test_keyed_ttl_cache_expires_and_drops_old_keys() -> None:
    now = [0.0]
    cache: KeyedTtlCache[str, int] = KeyedTtlCache(60.0, clock=lambda: now[0])
    assert cache.get("a") is None

    cache.set("a", 1)
    now[0] = 59.9
    assert cache.get("a") == 1
    now[0] = 60.0
    assert cache.get("a") is None

    cache.set("b", 2)
    assert list(cache.entries) == ["b"]
