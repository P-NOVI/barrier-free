from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_kakao_client
from app.main import app
from app.services.place_service import create_kakao_client

client = TestClient(app)

Handler = Callable[[httpx.Request], httpx.Response]

CITY_HALL = {
    "place_name": "서울특별시청",
    "address_name": "서울 중구 태평로1가 31",
    "road_address_name": "서울 중구 세종대로 110",
    "category_group_name": "공공기관",
    "x": "126.978652258309",
    "y": "37.566826004661",
    "distance": "120",
}


def respond_with(*documents: dict[str, str]) -> Handler:
    return lambda _: httpx.Response(200, json={"documents": list(documents)})


def time_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("시간 초과", request=request)


@pytest.fixture
def kakao() -> Iterator[Callable[[Handler], list[httpx.Request]]]:
    """카카오 API 대신 handler 가 응답하게 하고, 받은 요청 목록을 돌려준다."""

    def use(handler: Handler) -> list[httpx.Request]:
        received: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            received.append(request)
            return handler(request)

        settings = Settings(kakao_rest_api_key="test-key")

        def override() -> Iterator[httpx.Client]:
            transport = httpx.MockTransport(record)
            with create_kakao_client(settings, transport) as mock:
                yield mock

        app.dependency_overrides[get_kakao_client] = override
        return received

    yield use
    app.dependency_overrides.clear()


def test_search_returns_places(kakao) -> None:
    received = kakao(respond_with(CITY_HALL))

    response = client.get("/api/places/search", params={"query": "시청"})

    assert response.status_code == 200
    assert response.json() == {
        "places": [
            {
                "name": "서울특별시청",
                "address": "서울 중구 태평로1가 31",
                "road_address": "서울 중구 세종대로 110",
                "category": "공공기관",
                "position": [126.978652258309, 37.566826004661],
                "distance_m": 120.0,
            }
        ]
    }
    request = received[0]
    assert request.url.path == "/v2/local/search/keyword.json"
    assert request.headers["Authorization"] == "KakaoAK test-key"
    assert request.url.params["query"] == "시청"
    assert "sort" not in request.url.params


def test_search_near_coordinate_sends_center(kakao) -> None:
    received = kakao(respond_with(CITY_HALL))

    client.get(
        "/api/places/search",
        params={"query": " 시청 ", "lng": 126.9779, "lat": 37.5663, "size": 5},
    )

    params = received[0].url.params
    assert params["query"] == "시청"
    assert (params["x"], params["y"]) == ("126.9779", "37.5663")
    assert "sort" not in params
    assert params["size"] == "5"


def test_search_ignores_half_coordinate(kakao) -> None:
    received = kakao(respond_with())

    client.get("/api/places/search", params={"query": "시청", "lng": 126.9779})

    assert "x" not in received[0].url.params


def test_missing_optional_fields_become_empty(kakao) -> None:
    kakao(
        respond_with(
            CITY_HALL
            | {"road_address_name": "", "category_group_name": "", "distance": ""}
        )
    )

    place = client.get("/api/places/search", params={"query": "시청"}).json()["places"][
        0
    ]

    assert place["road_address"] == ""
    assert place["category"] == ""
    assert place["distance_m"] is None


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: httpx.Response(401, json={"errorType": "AccessDeniedError"}),
        lambda _: httpx.Response(200, text="not json"),
        lambda _: httpx.Response(200, json={"documents": [{"place_name": "x"}]}),
        time_out,
    ],
    ids=["unauthorized", "not-json", "missing-field", "timeout"],
)
def test_kakao_failure_is_bad_gateway(kakao, handler: Handler) -> None:
    kakao(handler)

    response = client.get("/api/places/search", params={"query": "시청"})

    assert response.status_code == 502
    assert response.json()["detail"]["reason"] == "search_failed"


def test_missing_key_is_unavailable() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(kakao_rest_api_key="")
    try:
        response = client.get("/api/places/search", params={"query": "시청"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "search_unavailable"


@pytest.mark.parametrize(
    "params",
    [{}, {"query": ""}, {"query": "   "}, {"query": "시청", "size": 16}],
    ids=["no-query", "empty", "blank", "size-over-limit"],
)
def test_invalid_query_is_rejected(kakao, params: dict[str, str | int]) -> None:
    received = kakao(respond_with())

    response = client.get("/api/places/search", params=params)

    assert response.status_code == 422
    assert received == []
