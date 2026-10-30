from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

KEYWORD_SEARCH_PATH = "/v2/local/search/keyword.json"
COORD_TO_ADDRESS_PATH = "/v2/local/geo/coord2address.json"
# 카카오 키워드 검색이 한 번에 돌려주는 최대 개수
MAX_PAGE_SIZE = 15
# 지도에서 누른 곳을 부를 때 쓰는 장소 분류 (카카오 category_name 앞부분)
LANDMARK_CATEGORIES = (
    "교통,수송 > 기차,철도",
    "교통,수송 > 지하철,전철",
    "교통,수송 > 교통시설",
    "여행 > 관광,명소",
    "여행 > 공원",
    "부동산 > 주거시설 > 아파트",
    "교육,학문 > 학교",
    "사회,공공기관 > 지방행정기관",
    "의료,건강 > 병원 > 대학병원",
    "문화,예술 > 문화시설",
    "가정,생활 > 백화점",
    "가정,생활 > 대형마트",
)


@dataclass(frozen=True)
class Place:
    name: str
    address: str
    road_address: str
    category: str
    position: tuple[float, float]
    distance_m: float | None


@dataclass(frozen=True)
class Address:
    name: str
    building_name: str
    road_address: str
    address: str


@dataclass(frozen=True)
class Lot:
    """coord2address 응답에서 이름을 정하는 데 쓰는 값"""

    building_name: str
    road_address: str
    address: str
    dong: str
    short_address: str


@dataclass(frozen=True)
class Landmark:
    name: str
    distance_m: float


class PlaceSearchError(Exception):
    """카카오 로컬 API 호출이나 응답 해석이 실패했을 때."""


def create_kakao_client(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    api_key = settings.kakao_rest_api_key.get_secret_value()
    return httpx.Client(
        base_url=settings.kakao_local_base_url,
        headers={"Authorization": f"KakaoAK {api_key}"},
        timeout=settings.kakao_timeout_s,
        transport=transport,
    )


def search_places(
    client: httpx.Client,
    query: str,
    near: tuple[float, float] | None = None,
    size: int = MAX_PAGE_SIZE,
) -> list[Place]:
    params: dict[str, str | int | float] = {"query": query, "size": size}
    if near is not None:
        # 정렬은 정확도순(카카오 기본값)으로 둔다. 거리순은 이름이 덜 맞는 가까운 곳을
        # 먼저 보여 준다. 좌표를 주면 근처 장소가 앞에 오고 distance 도 함께 온다.
        params |= {"x": near[0], "y": near[1]}
    return request_documents(
        client,
        KEYWORD_SEARCH_PATH,
        params,
        lambda documents: [to_place(document) for document in documents],
    )


def find_address(
    client: httpx.Client,
    position: tuple[float, float],
    landmark_radius_m: int,
    landmark_on_spot_m: float,
) -> Address | None:
    """좌표의 주소와 화면에 보일 이름. 바다처럼 주소가 없는 곳이면 None."""
    lot = request_documents(
        client,
        COORD_TO_ADDRESS_PATH,
        {"x": position[0], "y": position[1]},
        lambda documents: to_lot(documents[0]) if documents else None,
    )
    if lot is None:
        return None
    # 건물 이름이 있으면 그 이름을 쓰므로 근처를 찾지 않는다.
    landmark = (
        None
        if lot.building_name
        else nearest_landmark(client, position, lot.dong, landmark_radius_m)
    )
    return Address(
        name=location_name(lot, landmark, landmark_on_spot_m),
        building_name=lot.building_name,
        road_address=lot.road_address,
        address=lot.address,
    )


def nearest_landmark(
    client: httpx.Client, position: tuple[float, float], dong: str, radius_m: int
) -> Landmark | None:
    # 키워드 검색은 검색어가 필요하다. 동 이름으로 찾으면 주소가 그 동인 근처 장소가
    # 분류와 상관없이 거리순으로 온다.
    if not dong:
        return None
    landmarks = request_documents(
        client,
        KEYWORD_SEARCH_PATH,
        {
            "query": dong,
            "x": position[0],
            "y": position[1],
            "radius": radius_m,
            "sort": "distance",
            "size": MAX_PAGE_SIZE,
        },
        lambda documents: [
            Landmark(document["place_name"], float(document["distance"]))
            for document in documents
            if document.get("category_name", "").startswith(LANDMARK_CATEGORIES)
        ],
    )
    return min(landmarks, key=lambda landmark: landmark.distance_m, default=None)


def location_name(lot: Lot, landmark: Landmark | None, on_spot_m: float) -> str:
    """건물 이름 → 랜드마크 (멀면 'OO 부근') → 짧은 지번 주소"""
    # 건물 안 매장·창구도 랜드마크 분류로 잡히므로 건물 이름을 먼저 쓴다.
    if lot.building_name:
        return lot.building_name
    if landmark:
        near = landmark.distance_m > on_spot_m
        return f"{landmark.name} 부근" if near else landmark.name
    return lot.short_address


def request_documents[T](
    client: httpx.Client,
    path: str,
    params: dict[str, str | int | float],
    parse: Callable[[list[dict[str, Any]]], T],
) -> T:
    try:
        response = client.get(path, params=params)
        response.raise_for_status()
        return parse(response.json()["documents"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise PlaceSearchError from error


def to_place(document: dict[str, Any]) -> Place:
    # 기준 좌표 없이 검색하면 distance 는 빈 문자열로 온다.
    distance = document.get("distance")
    return Place(
        name=document["place_name"],
        address=document["address_name"],
        road_address=document.get("road_address_name") or "",
        category=document.get("category_group_name") or "",
        position=(float(document["x"]), float(document["y"])),
        distance_m=float(distance) if distance else None,
    )


def to_lot(document: dict[str, Any]) -> Lot:
    # 도로명 주소가 없는 땅이면 road_address 는 null 로 온다.
    road = document.get("road_address") or {}
    jibun = document["address"]
    dong = jibun.get("region_3depth_name") or ""
    number = "-".join(
        part
        for part in (jibun.get("main_address_no"), jibun.get("sub_address_no"))
        if part
    )
    if jibun.get("mountain_yn") == "Y":
        number = f"산 {number}"
    return Lot(
        building_name=road.get("building_name") or "",
        road_address=road.get("address_name") or "",
        address=jibun["address_name"],
        dong=dong,
        # 시·구를 뺀 "아현동 372-2". 동 이름이 없으면 전체 지번 주소
        short_address=f"{dong} {number}" if dong and number else jibun["address_name"],
    )
