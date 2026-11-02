from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, status

from app.config import Settings, get_settings
from app.repositories.road_repository import load_graph
from app.services.place_service import create_kakao_client
from core.graph import Graph

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_graph(settings: SettingsDep) -> Graph:
    try:
        return load_graph(settings.graph_path)
    except FileNotFoundError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": "graph_unavailable",
                "message": "경로 데이터가 없습니다. pipeline 04 단계를 확인하세요.",
            },
        ) from error


GraphDep = Annotated[Graph, Depends(get_graph)]


def get_kakao_client(settings: SettingsDep) -> Iterator[httpx.Client]:
    if not settings.kakao_rest_api_key.get_secret_value():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": "search_unavailable",
                "message": "장소 검색 키가 없습니다. backend/.env 의 "
                "KAKAO_REST_API_KEY 를 확인하세요.",
            },
        )
    with create_kakao_client(settings) as client:
        yield client


KakaoClientDep = Annotated[httpx.Client, Depends(get_kakao_client)]
