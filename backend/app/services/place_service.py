from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

KEYWORD_SEARCH_PATH = "/v2/local/search/keyword.json"
COORD_TO_ADDRESS_PATH = "/v2/local/geo/coord2address.json"
# 카카오 키워드 검색이 한 번에 돌려주는 최대 개수
MAX_PAGE_SIZE = 15


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
    building_name: str
    road_address: str
    address: str


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


def find_address(client: httpx.Client, position: tuple[float, float]) -> Address | None:
    """좌표의 주소. 바다처럼 주소가 없는 곳이면 None."""
    return request_documents(
        client,
        COORD_TO_ADDRESS_PATH,
        {"x": position[0], "y": position[1]},
        lambda documents: to_address(documents[0]) if documents else None,
    )


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


def to_address(document: dict[str, Any]) -> Address:
    # 도로명 주소가 없는 땅이면 road_address 는 null 로 온다.
    road = document.get("road_address") or {}
    return Address(
        building_name=road.get("building_name") or "",
        road_address=road.get("address_name") or "",
        address=document["address"]["address_name"],
    )
