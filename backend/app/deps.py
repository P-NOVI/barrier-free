from collections.abc import Iterator
from functools import cache
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_engine
from app.repositories.road_repository import load_graph
from app.repositories.sensor_repository import Sensor, load_sensors
from app.services.congestion_service import Reading, TtlCache, create_sdot_client
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


def get_sensors(settings: SettingsDep) -> dict[int, Sensor]:
    try:
        return load_sensors(settings.sensors_path)
    except FileNotFoundError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": "sensors_unavailable",
                "message": "센서 위치 데이터가 없습니다. "
                "pipeline 05 단계를 확인하세요.",
            },
        ) from error


SensorsDep = Annotated[dict[int, Sensor], Depends(get_sensors)]


def get_sdot_client(settings: SettingsDep) -> Iterator[httpx.Client]:
    if not settings.sdot_api_key.get_secret_value():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": "congestion_unavailable",
                "message": "혼잡도 키가 없습니다. backend/.env 의 "
                "SDOT_API_KEY 를 확인하세요.",
            },
        )
    with create_sdot_client(settings) as client:
        yield client


SdotClientDep = Annotated[httpx.Client, Depends(get_sdot_client)]


@cache
def get_congestion_cache() -> TtlCache[list[Reading]]:
    return TtlCache(get_settings().sdot_cache_ttl_s)


CongestionCacheDep = Annotated[TtlCache[list[Reading]], Depends(get_congestion_cache)]


def get_db_session(settings: SettingsDep) -> Iterator[Session]:
    database_url = settings.database_url.get_secret_value()
    if not database_url:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": "db_unavailable",
                "message": "DB 접속 주소가 없습니다. backend/.env 의 "
                "DATABASE_URL 을 확인하세요.",
            },
        )
    engine = get_engine(database_url, settings.database_connect_timeout_s)
    with Session(engine) as session:
        yield session


DbSessionDep = Annotated[Session, Depends(get_db_session)]
