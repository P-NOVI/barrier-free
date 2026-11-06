"""게스트·회원의 세션, 이동 조건, 검색·경로 이력, 즐겨찾기·내 장소·내 경로.

사용자는 쿠키(HttpOnly)의 토큰으로 찾는다. 이력을 처음 저장할 때 쿠키가 없으면
게스트를 만든다. 쿠키 없이 조회하면 빈 목록을 준다.
"""

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUserDep, DbSessionDep, SettingsDep, UserDep
from app.models import RouteHistory, SavedPlace, SavedRoute, SearchHistory
from app.repositories import (
    history_repository,
    place_repository,
    report_repository,
    saved_route_repository,
)
from app.repositories.user_repository import (
    linked_providers,
    load_preset,
    save_preset,
)
from app.routers.reports import FAILURE_MESSAGES, FAILURE_STATUS
from app.schemas import (
    PresetRequest,
    ReportListResponse,
    ReportResponse,
    ReportUpdateRequest,
    RouteError,
    RouteHistoryListResponse,
    RouteHistoryRequest,
    RouteHistoryResponse,
    SavedPlaceListResponse,
    SavedPlaceRequest,
    SavedPlaceResponse,
    SavedRouteListResponse,
    SavedRouteRequest,
    SavedRouteResponse,
    SearchHistoryListResponse,
    SearchHistoryRequest,
    SearchHistoryResponse,
    SessionResponse,
)
from app.services.report_service import ReportError, update_report
from core.profiles import DEFAULT_PRESET

router = APIRouter(tags=["me"])

NOT_FOUND = {
    404: {"model": RouteError, "description": "내 이력에 없는 id"},
}


def session_response(session: DbSessionDep, user_id: int | None) -> SessionResponse:
    if user_id is None:
        return SessionResponse(is_guest=True, providers=[], preset=DEFAULT_PRESET)
    providers = linked_providers(session, user_id)
    return SessionResponse(
        is_guest=not providers,
        providers=providers,
        preset=load_preset(session, user_id),
    )


def search_response(row: SearchHistory) -> SearchHistoryResponse:
    has_position = row.lon is not None and row.lat is not None
    return SearchHistoryResponse(
        id=row.id,
        query=row.query,
        place_name=row.place_name,
        address=row.address,
        position=(row.lon, row.lat) if has_position else None,
        created_at=row.created_at,
    )


def route_response(row: RouteHistory) -> RouteHistoryResponse:
    return RouteHistoryResponse(
        id=row.id,
        start_name=row.start_name,
        start=(row.start_lon, row.start_lat),
        goal_name=row.goal_name,
        goal=(row.goal_lon, row.goal_lat),
        preset=row.preset,
        distance_m=row.distance_m,
        created_at=row.created_at,
    )


def saved_route_response(row: SavedRoute) -> SavedRouteResponse:
    return SavedRouteResponse(
        id=row.id,
        start_name=row.start_name,
        start=(row.start_lon, row.start_lat),
        goal_name=row.goal_name,
        goal=(row.goal_lon, row.goal_lat),
        preset=row.preset,
        distance_m=row.distance_m,
        created_at=row.created_at,
    )


def place_response(row: SavedPlace) -> SavedPlaceResponse:
    return SavedPlaceResponse(
        id=row.id,
        kind=row.kind,
        label=row.label,
        name=row.name,
        address=row.address,
        position=(row.lon, row.lat),
        created_at=row.created_at,
    )


def delete_or_404(
    session: DbSessionDep,
    model: type[SearchHistory] | type[RouteHistory],
    user: CurrentUserDep,
    entry_id: int,
) -> None:
    if user is None or not history_repository.delete_entry(
        session, model, user.id, entry_id
    ):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"reason": "history_not_found", "message": "이력이 없습니다."},
        )
    session.commit()


@router.get("/session", response_model=SessionResponse)
def get_session(user: CurrentUserDep, session: DbSessionDep) -> SessionResponse:
    """쿠키의 사용자. 쿠키가 없어도 게스트를 만들지 않고 기본값을 준다."""
    return session_response(session, user.id if user else None)


@router.post("/session", response_model=SessionResponse)
def start_session(user: UserDep, session: DbSessionDep) -> SessionResponse:
    """쿠키의 사용자를 돌려준다. 쿠키가 없으면 게스트 토큰을 쿠키로 발급한다."""
    return session_response(session, user.id)


@router.put("/me/preset", response_model=SessionResponse)
def put_preset(
    request: PresetRequest, user: UserDep, session: DbSessionDep
) -> SessionResponse:
    save_preset(session, user.id, request.preset)
    session.commit()
    return session_response(session, user.id)


@router.get("/me/searches", response_model=SearchHistoryListResponse)
def get_searches(
    user: CurrentUserDep, session: DbSessionDep, settings: SettingsDep
) -> SearchHistoryListResponse:
    rows = (
        history_repository.list_searches(session, user.id, settings.history_keep)
        if user
        else []
    )
    return SearchHistoryListResponse(searches=[search_response(row) for row in rows])


@router.post(
    "/me/searches",
    response_model=SearchHistoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_search(
    request: SearchHistoryRequest,
    user: UserDep,
    session: DbSessionDep,
    settings: SettingsDep,
) -> SearchHistoryResponse:
    row = history_repository.add_search(
        session,
        user.id,
        settings.history_keep,
        request.query,
        request.place_name,
        request.address,
        request.position,
    )
    session.commit()
    return search_response(row)


@router.delete(
    "/me/searches/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND,
)
def delete_search(entry_id: int, user: CurrentUserDep, session: DbSessionDep) -> None:
    delete_or_404(session, SearchHistory, user, entry_id)


@router.delete("/me/searches", status_code=status.HTTP_204_NO_CONTENT)
def clear_searches(user: CurrentUserDep, session: DbSessionDep) -> None:
    if user:
        history_repository.clear(session, SearchHistory, user.id)
        session.commit()


@router.get("/me/routes", response_model=RouteHistoryListResponse)
def get_routes(
    user: CurrentUserDep, session: DbSessionDep, settings: SettingsDep
) -> RouteHistoryListResponse:
    rows = (
        history_repository.list_routes(session, user.id, settings.history_keep)
        if user
        else []
    )
    return RouteHistoryListResponse(routes=[route_response(row) for row in rows])


@router.post(
    "/me/routes",
    response_model=RouteHistoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_route_history(
    request: RouteHistoryRequest,
    user: UserDep,
    session: DbSessionDep,
    settings: SettingsDep,
) -> RouteHistoryResponse:
    row = history_repository.add_route(
        session,
        user.id,
        settings.history_keep,
        request.start_name,
        request.start,
        request.goal_name,
        request.goal,
        request.preset,
        request.distance_m,
    )
    session.commit()
    return route_response(row)


@router.delete(
    "/me/routes/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND,
)
def delete_route(entry_id: int, user: CurrentUserDep, session: DbSessionDep) -> None:
    delete_or_404(session, RouteHistory, user, entry_id)


@router.delete("/me/routes", status_code=status.HTTP_204_NO_CONTENT)
def clear_routes(user: CurrentUserDep, session: DbSessionDep) -> None:
    if user:
        history_repository.clear(session, RouteHistory, user.id)
        session.commit()


@router.get("/me/places", response_model=SavedPlaceListResponse)
def get_places(user: CurrentUserDep, session: DbSessionDep) -> SavedPlaceListResponse:
    rows = place_repository.list_places(session, user.id) if user else []
    return SavedPlaceListResponse(places=[place_response(row) for row in rows])


@router.post(
    "/me/places",
    response_model=SavedPlaceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": RouteError, "description": "저장할 수 있는 수를 넘음"}},
)
def post_place(
    request: SavedPlaceRequest,
    user: UserDep,
    session: DbSessionDep,
    settings: SettingsDep,
) -> SavedPlaceResponse:
    """같은 위치의 즐겨찾기, 같은 이름의 내 장소가 있으면 바꿔 저장한다."""
    try:
        row = place_repository.add_place(
            session,
            user.id,
            settings.saved_places_max,
            request.kind,
            request.label,
            request.name,
            request.address,
            request.position,
        )
    except place_repository.PlacesFullError as error:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"reason": "places_full", "message": str(error)},
        ) from error
    session.commit()
    return place_response(row)


@router.delete(
    "/me/places/{place_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": RouteError, "description": "내 장소에 없는 id"}},
)
def delete_place(place_id: int, user: CurrentUserDep, session: DbSessionDep) -> None:
    if user is None or not place_repository.delete_place(session, user.id, place_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"reason": "place_not_found", "message": "장소가 없습니다."},
        )
    session.commit()


def report_not_found() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail={"reason": "report_not_found", "message": "제보가 없습니다."},
    )


@router.get("/me/reports", response_model=ReportListResponse)
def get_reports(user: CurrentUserDep, session: DbSessionDep) -> ReportListResponse:
    rows = report_repository.list_reports(session, user.id) if user else []
    return ReportListResponse(
        reports=[
            ReportResponse.model_validate(row, from_attributes=True) for row in rows
        ]
    )


@router.patch(
    "/me/reports/{report_id}",
    response_model=ReportResponse,
    responses={
        404: {"model": RouteError, "description": "내 제보에 없는 id"},
        409: {"model": RouteError, "description": "검토가 끝나 고칠 수 없음"},
        422: {"model": RouteError},
    },
)
def patch_report(
    report_id: int,
    request: ReportUpdateRequest,
    user: CurrentUserDep,
    session: DbSessionDep,
) -> ReportResponse:
    report = report_repository.get_report(session, user.id, report_id) if user else None
    if report is None:
        raise report_not_found()
    try:
        update_report(report, request.kind, request.blocked, request.description)
    except ReportError as error:
        raise HTTPException(
            FAILURE_STATUS[error.reason],
            detail={
                "reason": error.reason,
                "message": FAILURE_MESSAGES[error.reason],
            },
        ) from error
    session.commit()
    return ReportResponse.model_validate(report, from_attributes=True)


@router.delete(
    "/me/reports/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": RouteError, "description": "내 제보에 없는 id"}},
)
def delete_report(
    report_id: int,
    user: CurrentUserDep,
    session: DbSessionDep,
    settings: SettingsDep,
) -> None:
    photo_name = (
        report_repository.delete_report(session, user.id, report_id) if user else None
    )
    if photo_name is None:
        raise report_not_found()
    session.commit()
    # DB 에서 지운 뒤에 파일을 지워, 커밋이 실패해도 사진만 사라지는 일이 없게 한다.
    (settings.report_photo_dir / photo_name).unlink(missing_ok=True)


@router.get("/me/saved-routes", response_model=SavedRouteListResponse)
def get_saved_routes(
    user: CurrentUserDep, session: DbSessionDep
) -> SavedRouteListResponse:
    rows = saved_route_repository.list_saved_routes(session, user.id) if user else []
    return SavedRouteListResponse(routes=[saved_route_response(row) for row in rows])


@router.post(
    "/me/saved-routes",
    response_model=SavedRouteResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": RouteError, "description": "저장할 수 있는 수를 넘음"}},
)
def post_saved_route(
    request: SavedRouteRequest,
    user: UserDep,
    session: DbSessionDep,
    settings: SettingsDep,
) -> SavedRouteResponse:
    """출발·도착 위치와 이동 조건이 같은 경로가 있으면 바꿔 저장한다."""
    try:
        row = saved_route_repository.add_saved_route(
            session,
            user.id,
            settings.saved_routes_max,
            request.start_name,
            request.start,
            request.goal_name,
            request.goal,
            request.preset,
            request.distance_m,
        )
    except saved_route_repository.SavedRoutesFullError as error:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"reason": "saved_routes_full", "message": str(error)},
        ) from error
    session.commit()
    return saved_route_response(row)


@router.delete(
    "/me/saved-routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": RouteError, "description": "내 경로에 없는 id"}},
)
def delete_saved_route(
    route_id: int, user: CurrentUserDep, session: DbSessionDep
) -> None:
    if user is None or not saved_route_repository.delete_saved_route(
        session, user.id, route_id
    ):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"reason": "saved_route_not_found", "message": "경로가 없습니다."},
        )
    session.commit()
