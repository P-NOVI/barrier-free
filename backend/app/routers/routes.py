from collections.abc import Mapping
from datetime import datetime, time, timedelta

from fastapi import APIRouter, HTTPException, status

from app.deps import (
    EntrancesDep,
    ForecastCongestionDep,
    RealtimeCongestionDep,
    RouteGraphDep,
    SettingsDep,
    SitesDep,
)
from app.schemas import (
    RouteError,
    RouteOption,
    RouteRequest,
    RouteResponse,
    TurnPoint,
)
from app.services.congestion_service import KST
from app.services.route_service import (
    Route,
    RouteFailure,
    RouteNotFoundError,
    busy_length,
    find_routes,
)
from core.profiles import PRESETS

router = APIRouter(tags=["route"])

FAILURE_STATUS = {
    RouteFailure.START_OFF_NETWORK: status.HTTP_422_UNPROCESSABLE_CONTENT,
    RouteFailure.GOAL_OFF_NETWORK: status.HTTP_422_UNPROCESSABLE_CONTENT,
    RouteFailure.NO_PATH: status.HTTP_404_NOT_FOUND,
}


FAILURE_MESSAGES = {
    RouteFailure.START_OFF_NETWORK: "출발지 {gap} 안에 보행 도로가 없습니다.",
    RouteFailure.GOAL_OFF_NETWORK: "도착지 {gap} 안에 보행 도로가 없습니다.",
    RouteFailure.NO_PATH: "이동 조건에 맞는 경로가 없습니다.",
}


def failure_message(reason: RouteFailure, max_snap_distance_m: float) -> str:
    return FAILURE_MESSAGES[reason].format(gap=f"{max_snap_distance_m:.0f}m")


def depart_slot(
    depart_at: datetime | None, now: datetime, days: int
) -> datetime | None:
    """출발 시각 → 그 시각이 든 한 시간의 시작(한국 시각). 지금이면 None.

    시간대가 없으면 한국 시각으로 본다. 지금 시 ~ 오늘부터 days 일째 23시만 받는다.
    ValueError: 그 밖의 시각
    """
    if depart_at is None:
        return None
    if depart_at.tzinfo is None:
        depart_at = depart_at.replace(tzinfo=KST)
    slot = depart_at.astimezone(KST).replace(minute=0, second=0, microsecond=0)
    first = now.astimezone(KST).replace(minute=0, second=0, microsecond=0)
    last = datetime.combine(first.date() + timedelta(days=days), time(), tzinfo=KST)
    if not first <= slot < last:
        raise ValueError(slot)
    return slot


def route_option(
    route: Route, congestion: Mapping[int, float], busy_level: float
) -> RouteOption:
    summary = route.summary
    return RouteOption(
        distance_m=summary.distance_m,
        duration_s=route.duration_s,
        max_grade=summary.max_grade,
        ascent_m=summary.ascent_m,
        steps_count=summary.steps_count,
        coordinates=route.coordinates,
        elevations=route.elevations,
        distances_m=route.distances_m,
        turns=[TurnPoint(index=turn.index, angle=turn.angle) for turn in route.turns],
        start_gap_m=route.start_gap_m,
        goal_gap_m=route.goal_gap_m,
        start_entrance=route.start_entrance,
        goal_entrance=route.goal_entrance,
        busy_m=busy_length(route, congestion, busy_level),
    )


@router.post(
    "/route",
    response_model=RouteResponse,
    responses={404: {"model": RouteError}, 422: {"model": RouteError}},
)
def post_route(
    request: RouteRequest,
    graph: RouteGraphDep,
    entrances: EntrancesDep,
    sites: SitesDep,
    realtime: RealtimeCongestionDep,
    forecast: ForecastCongestionDep,
    settings: SettingsDep,
) -> RouteResponse:
    """1안(혼잡도 없이)과, 출발 시각의 혼잡도로 찾은 2안(1안과 다를 때만)."""
    try:
        slot = depart_slot(
            request.depart_at, datetime.now(KST), settings.route_forecast_days
        )
    except ValueError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "reason": "invalid_depart_at",
                "message": "출발 시각은 지금부터 모레 23시까지만 고를 수 있습니다.",
            },
        ) from error
    congestion = realtime() if slot is None else forecast(slot)
    try:
        choice = find_routes(
            graph,
            request.start,
            request.goal,
            PRESETS[request.preset],
            settings.max_snap_distance_m,
            entrances,
            sites,
            congestion,
            settings.congestion_busy_level,
        )
    except RouteNotFoundError as error:
        raise HTTPException(
            FAILURE_STATUS[error.reason],
            detail={
                "reason": error.reason,
                "message": failure_message(error.reason, settings.max_snap_distance_m),
            },
        ) from error
    level = settings.congestion_busy_level
    primary = route_option(choice.primary, congestion, level)
    alternative = (
        None
        if choice.alternative is None
        else route_option(choice.alternative, congestion, level)
    )
    return RouteResponse(**primary.model_dump(), alternative=alternative)
