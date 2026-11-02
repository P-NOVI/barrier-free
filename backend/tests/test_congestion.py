from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_congestion_cache, get_sdot_client, get_sensors
from app.main import app
from app.repositories.sensor_repository import Sensor
from app.services.congestion_service import Reading, TtlCache, create_sdot_client

client = TestClient(app)

Handler = Callable[[httpx.Request], httpx.Response]

SENSORS = {
    3032: Sensor(3032, (126.84, 37.54), "서울특별시 강서구 화곡동 668-10"),
    3022: Sensor(3022, (126.92, 37.47), "서울특별시 관악구 신원로 3다길 1"),
}


def row(serial: str, count: str, sensing_time: str = "2026-11-02_11:18:00") -> dict:
    return {
        "MODELNAME": "SDOT001",
        "SERIAL": serial,
        "SENSING_TIME": sensing_time,
        "VISITOR_COUNT": count,
    }


def respond_with(*rows: dict) -> Handler:
    body = {
        "sDoTPeople": {
            "list_total_count": len(rows),
            "RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다"},
            "row": list(rows),
        }
    }
    return lambda _: httpx.Response(200, json=body)


def respond_with_code(code: str) -> Handler:
    body = {"RESULT": {"CODE": code, "MESSAGE": "메시지"}}
    return lambda _: httpx.Response(200, json=body)


def time_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("시간 초과", request=request)


@pytest.fixture
def sdot() -> Iterator[Callable[[Handler], list[httpx.Request]]]:
    """S-DoT API 대신 handler 가 응답하게 하고, 받은 요청 목록을 돌려준다."""

    def use(handler: Handler) -> list[httpx.Request]:
        received: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            received.append(request)
            return handler(request)

        settings = Settings(sdot_api_key="test-key")

        def override() -> Iterator[httpx.Client]:
            with create_sdot_client(settings, httpx.MockTransport(record)) as mock:
                yield mock

        app.dependency_overrides[get_sdot_client] = override
        app.dependency_overrides[get_sensors] = lambda: SENSORS
        app.dependency_overrides[get_congestion_cache] = lambda: cache
        return received

    cache: TtlCache[list[Reading]] = TtlCache(60.0)
    yield use
    app.dependency_overrides.clear()


def test_returns_latest_reading_per_known_sensor(sdot) -> None:
    received = sdot(
        respond_with(
            row("00000003032", "208", "2026-11-02_11:18:00"),
            row("00000003032", "150", "2026-11-02_11:08:00"),
            row("00000003022", "181"),
            row("00000009999", "10"),
        )
    )

    response = client.get("/api/congestion")

    assert response.status_code == 200
    assert response.json() == {
        "sensors": [
            {
                "code": 3022,
                "position": [126.92, 37.47],
                "address": "서울특별시 관악구 신원로 3다길 1",
                "visitor_count": 181,
                "measured_at": "2026-11-02T11:18:00+09:00",
            },
            {
                "code": 3032,
                "position": [126.84, 37.54],
                "address": "서울특별시 강서구 화곡동 668-10",
                "visitor_count": 208,
                "measured_at": "2026-11-02T11:18:00+09:00",
            },
        ]
    }
    request = received[0]
    assert request.url.path == "/test-key/json/sDoTPeople/1/1000/"


def test_skips_broken_rows(sdot) -> None:
    sdot(
        respond_with(
            row("abc", "10"),
            row("00000003032", "많음"),
            row("00000003032", "30", "어제"),
            row("00000003022", "181"),
        )
    )

    response = client.get("/api/congestion")

    assert [item["code"] for item in response.json()["sensors"]] == [3022]


def test_cache_avoids_second_call(sdot) -> None:
    received = sdot(respond_with(row("00000003032", "208")))

    client.get("/api/congestion")
    second = client.get("/api/congestion")

    assert second.status_code == 200
    assert len(received) == 1


def test_no_data_code_returns_empty_list(sdot) -> None:
    sdot(respond_with_code("INFO-200"))

    response = client.get("/api/congestion")

    assert response.status_code == 200
    assert response.json() == {"sensors": []}


@pytest.mark.parametrize(
    "handler",
    [
        respond_with_code("INFO-100"),
        respond_with_code("ERROR-500"),
        lambda _: httpx.Response(500),
        lambda _: httpx.Response(200, text="<html>점검 중</html>"),
        time_out,
    ],
)
def test_upstream_failure_is_502_without_key(sdot, handler) -> None:
    sdot(handler)

    response = client.get("/api/congestion")

    assert response.status_code == 502
    assert response.json()["detail"]["reason"] == "congestion_failed"
    assert "test-key" not in response.text


def test_failure_is_not_cached(sdot) -> None:
    received = sdot(respond_with_code("ERROR-500"))

    client.get("/api/congestion")
    client.get("/api/congestion")

    assert len(received) == 2


def test_missing_key_is_503() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, sdot_api_key=""
    )
    try:
        response = client.get("/api/congestion")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "congestion_unavailable"


def test_missing_sensor_file_is_503(tmp_path) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        sdot_api_key="test-key",
        sensors_path=tmp_path / "none.json",
    )
    try:
        response = client.get("/api/congestion")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "sensors_unavailable"


def test_ttl_cache_expires() -> None:
    now = [0.0]
    cache: TtlCache[int] = TtlCache(60.0, clock=lambda: now[0])
    assert cache.get() is None

    cache.set(1)
    now[0] = 59.9
    assert cache.get() == 1
    now[0] = 60.0
    assert cache.get() is None
