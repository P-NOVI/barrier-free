from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.deps import KakaoClientDep, SettingsDep
from app.schemas import (
    AddressLookupResponse,
    AddressResponse,
    PlaceResponse,
    PlaceSearchResponse,
    RouteError,
)
from app.services.place_service import (
    MAX_PAGE_SIZE,
    PlaceSearchError,
    find_address,
    search_places,
)

router = APIRouter(tags=["place"])

KAKAO_ERRORS = {502: {"model": RouteError}, 503: {"model": RouteError}}


def kakao_failed(message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        detail={"reason": "search_failed", "message": message},
    )


@router.get(
    "/places/search",
    response_model=PlaceSearchResponse,
    responses=KAKAO_ERRORS,
)
def get_places(
    client: KakaoClientDep,
    # 공백만 있는 검색어는 받지 않는다.
    query: Annotated[str, Query(min_length=1, max_length=100, pattern=r"\S")],
    lng: Annotated[
        float | None,
        Query(
            ge=-180,
            le=180,
            description="lat 과 함께 주면 그 근처를 우선하고 거리를 돌려준다",
        ),
    ] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
) -> PlaceSearchResponse:
    near = (lng, lat) if lng is not None and lat is not None else None
    try:
        places = search_places(client, query.strip(), near, size)
    except PlaceSearchError as error:
        raise kakao_failed(
            "장소 검색에 실패했습니다. 잠시 뒤 다시 시도하세요."
        ) from error
    return PlaceSearchResponse(
        places=[PlaceResponse(**asdict(place)) for place in places]
    )


@router.get(
    "/places/address",
    response_model=AddressLookupResponse,
    responses=KAKAO_ERRORS,
)
def get_address(
    client: KakaoClientDep,
    settings: SettingsDep,
    lng: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
) -> AddressLookupResponse:
    try:
        address = find_address(client, (lng, lat), settings)
    except PlaceSearchError as error:
        raise kakao_failed(
            "주소를 찾지 못했습니다. 잠시 뒤 다시 시도하세요."
        ) from error
    return AddressLookupResponse(
        address=AddressResponse(**asdict(address)) if address else None
    )
