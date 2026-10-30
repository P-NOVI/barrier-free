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


def respond_with(*documents: dict[str, object]) -> Handler:
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


AHYEON_LOT = {
    "road_address": None,
    "address": {
        "address_name": "서울 마포구 아현동 372-2",
        "region_3depth_name": "아현동",
        "mountain_yn": "N",
        "main_address_no": "372",
        "sub_address_no": "2",
    },
}
BUILDING_LOT = AHYEON_LOT | {
    "road_address": {
        "address_name": "서울특별시 마포구 마포대로 100",
        "building_name": "현대빌딩",
    }
}


def place(name: str, distance: int, category: str, group: str = "") -> dict[str, str]:
    return {
        "place_name": name,
        "distance": str(distance),
        "category_name": category,
        "category_group_code": group,
    }


PARK = "여행 > 공원"
APARTMENT = "부동산 > 주거시설 > 아파트 > 아파트 동"
CAFE = "음식점 > 카페"
WHOLESALE = "서비스,산업 > 식품 > 음료,주류제조 > 주류도매,주류유통"


def kakao_local(lot: dict[str, object] | None, *nearby: dict[str, str]) -> Handler:
    """coord2address 는 lot, 키워드 검색은 nearby 로 답한다."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("coord2address.json"):
            return httpx.Response(200, json={"documents": [lot] if lot else []})
        return httpx.Response(200, json={"documents": list(nearby)})

    return handle


def address_of(params: dict[str, float] | None = None) -> dict[str, str] | None:
    response = client.get(
        "/api/places/address", params=params or {"lng": 126.9584, "lat": 37.5549}
    )
    assert response.status_code == 200
    return response.json()["address"]


def test_address_fields(kakao) -> None:
    received = kakao(kakao_local(BUILDING_LOT, place("애오개어린이공원", 5, PARK)))

    address = address_of()

    assert address == {
        "name": "현대빌딩",
        "building_name": "현대빌딩",
        "road_address": "서울특별시 마포구 마포대로 100",
        "address": "서울 마포구 아현동 372-2",
    }
    # 건물 이름이 있으면 근처 장소를 찾지 않는다.
    assert len(received) == 1


def test_nearby_search_request(kakao) -> None:
    received = kakao(kakao_local(AHYEON_LOT))

    address_of({"lng": 126.9584, "lat": 37.5549})

    coord, nearby = received
    assert coord.url.path == "/v2/local/geo/coord2address.json"
    assert (coord.url.params["x"], coord.url.params["y"]) == ("126.9584", "37.5549")
    assert nearby.url.params["query"] == "아현동"
    assert nearby.url.params["radius"] == "60"
    assert nearby.url.params["sort"] == "distance"


@pytest.mark.parametrize(
    ("lot", "nearby", "name"),
    [
        pytest.param(
            AHYEON_LOT,
            [place("애오개어린이공원", 5, PARK)],
            "애오개어린이공원",
            id="landmark-on-spot",
        ),
        pytest.param(
            AHYEON_LOT,
            [place("공덕자이아파트 201동", 43, APARTMENT)],
            "공덕자이아파트 201동 부근",
            id="far-landmark-without-building",
        ),
        pytest.param(
            AHYEON_LOT,
            [
                place("애오개어린이공원", 15, PARK),
                place("낫배드커피 한남", 8, CAFE, "CE7"),
            ],
            "낫배드커피 한남",
            id="shop-on-spot",
        ),
        pytest.param(
            AHYEON_LOT,
            [
                place("뉴욕브라우니코리아", 0, WHOLESALE),
                place("낫배드커피 한남", 0, CAFE, "CE7"),
            ],
            "낫배드커피 한남",
            id="shop-beats-office-at-same-spot",
        ),
        pytest.param(
            AHYEON_LOT,
            [place("동서재 닭강정", 25, CAFE, "CE7")],
            "아현동 372-2",
            id="far-shops-are-not-landmarks",
        ),
        pytest.param(
            AHYEON_LOT,
            [
                place("동서재 닭강정", 25, CAFE, "CE7"),
                place("애오개어린이공원", 27, PARK),
            ],
            "애오개어린이공원",
            id="landmark-beats-far-shop",
        ),
        pytest.param(AHYEON_LOT, [], "아현동 372-2", id="short-address"),
    ],
)
def test_location_name(kakao, lot, nearby, name) -> None:
    kakao(kakao_local(lot, *nearby))

    assert address_of()["name"] == name


def test_mountain_lot_name(kakao) -> None:
    mountain = AHYEON_LOT | {
        "address": AHYEON_LOT["address"] | {"mountain_yn": "Y", "sub_address_no": ""}
    }
    kakao(kakao_local(mountain))

    assert address_of()["name"] == "아현동 산 372"


def test_coordinate_without_address_is_null(kakao) -> None:
    received = kakao(kakao_local(None))

    assert address_of({"lng": 126.5, "lat": 37.0}) is None
    assert len(received) == 1


def test_address_kakao_failure_is_bad_gateway(kakao) -> None:
    kakao(time_out)

    response = client.get("/api/places/address", params={"lng": 126.97, "lat": 37.55})

    assert response.status_code == 502
    assert response.json()["detail"]["reason"] == "search_failed"


@pytest.mark.parametrize(
    "params",
    [{"lng": 126.97}, {"lng": 181, "lat": 37.55}, {"lng": 126.97, "lat": -91}],
    ids=["no-lat", "lng-out-of-range", "lat-out-of-range"],
)
def test_invalid_coordinate_is_rejected(kakao, params: dict[str, float]) -> None:
    received = kakao(respond_with())

    response = client.get("/api/places/address", params=params)

    assert response.status_code == 422
    assert received == []
