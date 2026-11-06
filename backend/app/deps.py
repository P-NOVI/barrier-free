import logging
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from functools import cache
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collector.store import collector_engine
from app.config import Settings, get_settings
from app.db import get_engine
from app.models import Report, User, utc_now
from app.repositories.closure_repository import closed_edge_ids
from app.repositories.report_repository import list_reviewable_reports
from app.repositories.road_repository import load_entrances, load_graph, load_sites
from app.repositories.sensor_repository import Sensor, load_sensors
from app.repositories.user_repository import (
    create_guest,
    find_user_by_token,
    has_social_account,
)
from app.services.congestion_service import (
    KST,
    Reading,
    TtlCache,
    create_sdot_client,
    road_congestion,
)
from app.services.forecast_congestion_service import (
    ForecastCache,
    forecast_congestion,
)
from app.services.oauth_service import create_oauth_client
from app.services.place_service import create_kakao_client
from app.services.weather_service import ItemCache, KeyedTtlCache, create_kma_client
from core.closure import close_edges
from core.entrance import EntranceIndex
from core.graph import Graph
from core.site import SiteIndex

logger = logging.getLogger(__name__)

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


def get_entrances(settings: SettingsDep) -> EntranceIndex:
    return load_entrances(settings.entrances_path)


EntrancesDep = Annotated[EntranceIndex, Depends(get_entrances)]


def get_sites(settings: SettingsDep) -> SiteIndex:
    return load_sites(settings.sites_path)


SitesDep = Annotated[SiteIndex, Depends(get_sites)]


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


@cache
def get_road_congestion_cache() -> TtlCache[dict[int, float]]:
    return TtlCache(get_settings().sdot_cache_ttl_s)


RoadCongestionCacheDep = Annotated[
    TtlCache[dict[int, float]], Depends(get_road_congestion_cache)
]


def get_road_congestion(
    graph: GraphDep,
    settings: SettingsDep,
    readings: CongestionCacheDep,
    cache: RoadCongestionCacheDep,
) -> dict[int, float]:
    """경로 탐색에 쓰는 길별 혼잡도(0~1).

    S-DoT 키나 센서 위치 파일이 없으면 비워서, 경로는 혼잡 없이 찾는다.
    """
    if not settings.sdot_api_key.get_secret_value():
        return {}
    try:
        sensors = load_sensors(settings.sensors_path)
    except FileNotFoundError:
        return {}
    return road_congestion(graph, sensors, settings, readings, cache)


RoadCongestionDep = Annotated[dict[int, float], Depends(get_road_congestion)]

# 경로 요청의 출발 시각에 따라 둘 중 하나만 부른다. 출발 시각을 고르면 S-DoT 를,
# 지금이면 수집 DB를 부르지 않도록 바로 구하지 않고 함수로 넘긴다.
RealtimeCongestion = Callable[[], dict[int, float]]
ForecastCongestion = Callable[[datetime], dict[int, float]]


def get_realtime_congestion(
    graph: GraphDep,
    settings: SettingsDep,
    readings: CongestionCacheDep,
    cache: RoadCongestionCacheDep,
) -> RealtimeCongestion:
    """지금(실시간 S-DoT) 길별 혼잡도를 구하는 함수."""
    return lambda: get_road_congestion(graph, settings, readings, cache)


RealtimeCongestionDep = Annotated[RealtimeCongestion, Depends(get_realtime_congestion)]


@cache
def get_forecast_cache() -> ForecastCache:
    return KeyedTtlCache(get_settings().forecast_cache_ttl_s)


ForecastCacheDep = Annotated[ForecastCache, Depends(get_forecast_cache)]


def get_forecast_congestion(
    graph: GraphDep, settings: SettingsDep, cache: ForecastCacheDep
) -> ForecastCongestion:
    """시각(한 시간의 시작)의 예측 길별 혼잡도를 구하는 함수.

    수집 DB 주소나 센서 위치 파일이 없으면 빈 값이라, 경로는 1안만 나온다.
    """

    def levels(slot: datetime) -> dict[int, float]:
        database_url = settings.collector_database_url.get_secret_value()
        if not database_url:
            return {}
        try:
            sensors = load_sensors(settings.sensors_path)
        except FileNotFoundError:
            return {}
        engine = collector_engine(database_url, settings.collector_connect_timeout_s)
        today = datetime.now(KST).date()
        return forecast_congestion(engine, graph, sensors, settings, slot, today, cache)

    return levels


ForecastCongestionDep = Annotated[ForecastCongestion, Depends(get_forecast_congestion)]


@cache
def get_closed_road_cache() -> TtlCache[frozenset[int]]:
    return TtlCache(get_settings().closed_road_cache_ttl_s)


ClosedRoadCacheDep = Annotated[TtlCache[frozenset[int]], Depends(get_closed_road_cache)]


def get_closed_edges(
    settings: SettingsDep, cache: ClosedRoadCacheDep
) -> frozenset[int]:
    """경로 탐색에서 뺄 길(승인된 통행 불가 제보).

    DB가 없거나 읽지 못하면 비워서, 경로는 지금처럼 막힌 길 없이 찾는다.
    읽지 못한 결과도 캐시해 DB가 꺼진 동안 요청마다 접속을 기다리지 않는다.
    """
    cached = cache.get()
    if cached is not None:
        return cached
    edge_ids: frozenset[int] = frozenset()
    database_url = settings.database_url.get_secret_value()
    if database_url:
        engine = get_engine(database_url, settings.database_connect_timeout_s)
        try:
            with Session(engine) as session:
                edge_ids = closed_edge_ids(session, utc_now())
        except SQLAlchemyError as error:
            # 오류 문구에 접속 정보가 섞일 수 있어 종류만 남긴다.
            logger.warning(
                "막힌 길을 읽지 못해 빼지 않고 경로를 찾습니다 (%s).",
                type(error).__name__,
            )
    cache.set(edge_ids)
    return edge_ids


ClosedEdgesDep = Annotated[frozenset[int], Depends(get_closed_edges)]


ReportFinder = Callable[[frozenset[int]], list[Report]]


def get_report_finder(settings: SettingsDep) -> ReportFinder:
    """경로가 지나는 길(edge_id)에 붙은 리뷰 대상 제보를 찾는 함수.

    DB가 없거나 읽지 못하면 빈 목록을 줘서, 경로 응답은 제보 없이 돌려준다.
    """

    def find(edge_ids: frozenset[int]) -> list[Report]:
        database_url = settings.database_url.get_secret_value()
        if not edge_ids or not database_url:
            return []
        engine = get_engine(database_url, settings.database_connect_timeout_s)
        try:
            with Session(engine) as session:
                return list_reviewable_reports(session, edge_ids, utc_now())
        except SQLAlchemyError as error:
            # 오류 문구에 접속 정보가 섞일 수 있어 종류만 남긴다.
            logger.warning(
                "경로가 지나는 제보를 읽지 못해 빼고 응답합니다 (%s).",
                type(error).__name__,
            )
            return []

    return find


ReportFinderDep = Annotated[ReportFinder, Depends(get_report_finder)]


def get_route_graph(graph: GraphDep, closed: ClosedEdgesDep) -> Graph:
    """경로 탐색용 그래프. 승인된 통행 불가 제보의 길은 지나갈 수 없다."""
    return close_edges(graph, closed)


RouteGraphDep = Annotated[Graph, Depends(get_route_graph)]


def get_kma_client(settings: SettingsDep) -> Iterator[httpx.Client]:
    if not settings.kma_api_key.get_secret_value():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": "weather_unavailable",
                "message": "날씨 키가 없습니다. backend/.env 의 "
                "KMA_API_KEY 를 확인하세요.",
            },
        )
    with create_kma_client(settings) as client:
        yield client


KmaClientDep = Annotated[httpx.Client, Depends(get_kma_client)]


@cache
def get_weather_cache() -> ItemCache:
    return KeyedTtlCache(get_settings().kma_cache_ttl_s)


WeatherCacheDep = Annotated[ItemCache, Depends(get_weather_cache)]


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


def set_token_cookie(response: Response, settings: Settings, token: str) -> None:
    # 쓸 때마다 다시 줘서, 계속 쓰는 동안에는 브라우저에서 만료되지 않게 한다.
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        max_age=int(timedelta(days=settings.token_idle_days).total_seconds()),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )


def get_current_user(
    request: Request, response: Response, session: DbSessionDep, settings: SettingsDep
) -> User | None:
    """쿠키 토큰의 사용자. 쿠키가 없거나 만료됐으면 None."""
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    user = find_user_by_token(session, token, settings.token_idle_days)
    if user is None:
        return None
    session.commit()
    set_token_cookie(response, settings, token)
    return user


CurrentUserDep = Annotated[User | None, Depends(get_current_user)]


def ensure_user(
    user: CurrentUserDep,
    response: Response,
    session: DbSessionDep,
    settings: SettingsDep,
) -> User:
    """쿠키 토큰의 사용자. 없으면 게스트를 만들고 토큰을 쿠키로 준다."""
    if user is not None:
        return user
    user, token = create_guest(session)
    session.commit()
    set_token_cookie(response, settings, token)
    return user


UserDep = Annotated[User, Depends(ensure_user)]


def get_admin_user(
    user: CurrentUserDep, session: DbSessionDep, settings: SettingsDep
) -> User:
    """관리자 계정의 사용자. 쿠키가 없으면 401, 관리자가 아니면(게스트 포함) 403."""
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "login_required", "message": "로그인이 필요합니다."},
        )
    if not has_social_account(session, user.id, settings.admin_account_set):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"reason": "admin_only", "message": "관리자만 쓸 수 있습니다."},
        )
    return user


AdminUserDep = Annotated[User, Depends(get_admin_user)]


def get_oauth_client(settings: SettingsDep) -> Iterator[httpx.Client]:
    with create_oauth_client(settings) as client:
        yield client


OAuthClientDep = Annotated[httpx.Client, Depends(get_oauth_client)]
