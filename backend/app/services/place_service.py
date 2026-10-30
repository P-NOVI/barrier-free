from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

KEYWORD_SEARCH_PATH = "/v2/local/search/keyword.json"
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
        params |= {"x": near[0], "y": near[1], "sort": "distance"}
    try:
        response = client.get(KEYWORD_SEARCH_PATH, params=params)
        response.raise_for_status()
        return [to_place(document) for document in response.json()["documents"]]
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
