"""게스트·회원의 세션, 이동 조건, 검색·경로 이력.

사용자는 쿠키(HttpOnly)의 토큰으로 찾는다. 이력을 처음 저장할 때 쿠키가 없으면
게스트를 만든다. 쿠키 없이 조회하면 빈 목록을 준다.
"""

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUserDep, DbSessionDep, SettingsDep, UserDep
from app.models import RouteHistory, SearchHistory
from app.repositories import history_repository
from app.repositories.user_repository import is_guest, load_preset, save_preset
from app.schemas import (
    PresetRequest,
    RouteError,
    RouteHistoryListResponse,
    RouteHistoryRequest,
    RouteHistoryResponse,
    SearchHistoryListResponse,
    SearchHistoryRequest,
    SearchHistoryResponse,
    SessionResponse,
)

router = APIRouter(tags=["me"])

NOT_FOUND = {
    404: {"model": RouteError, "description": "내 이력에 없는 id"},
}


def session_response(session: DbSessionDep, user_id: int) -> SessionResponse:
    return SessionResponse(
        is_guest=is_guest(session, user_id), preset=load_preset(session, user_id)
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
