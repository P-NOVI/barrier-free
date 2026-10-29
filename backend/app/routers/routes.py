from fastapi import APIRouter, HTTPException, status

from app.deps import GraphDep, SettingsDep
from app.schemas import RouteError, RouteRequest, RouteResponse
from app.services.route_service import RouteFailure, RouteNotFoundError, find_route
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


@router.post(
    "/route",
    response_model=RouteResponse,
    responses={404: {"model": RouteError}, 422: {"model": RouteError}},
)
def post_route(
    request: RouteRequest, graph: GraphDep, settings: SettingsDep
) -> RouteResponse:
    try:
        route = find_route(
            graph,
            request.start,
            request.goal,
            PRESETS[request.preset],
            settings.max_snap_distance_m,
        )
    except RouteNotFoundError as error:
        raise HTTPException(
            FAILURE_STATUS[error.reason],
            detail={
                "reason": error.reason,
                "message": failure_message(error.reason, settings.max_snap_distance_m),
            },
        ) from error
    summary = route.summary
    return RouteResponse(
        distance_m=summary.distance_m,
        max_grade=summary.max_grade,
        ascent_m=summary.ascent_m,
        steps_count=summary.steps_count,
        coordinates=route.coordinates,
        elevations=route.elevations,
        distances_m=route.distances_m,
    )
