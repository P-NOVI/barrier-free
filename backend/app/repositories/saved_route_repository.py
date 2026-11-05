"""즐겨찾기한 경로(내 경로). 함수는 commit 하지 않는다.

출발·도착 위치와 이동 조건이 같은 경로는 하나만 둔다. 다시 저장하면 예전 것을 지운다.
"""

from typing import Any

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.orm import Session

from app.models import SavedRoute

Position = tuple[float, float]


class SavedRoutesFullError(Exception):
    """사용자가 저장할 수 있는 경로 수를 넘었다."""


def same_route(
    row: type[SavedRoute],
    start: tuple[Any, Any],
    goal: tuple[Any, Any],
    preset: Any,
) -> ColumnElement[bool]:
    """row 의 출발·도착 위치와 이동 조건이 같은지. 값이나 다른 행의 칸과 견준다."""
    return (
        (row.start_lon == start[0])
        & (row.start_lat == start[1])
        & (row.goal_lon == goal[0])
        & (row.goal_lat == goal[1])
        & (row.preset == preset)
    )


def add_saved_route(
    session: Session,
    user_id: int,
    max_routes: int,
    start_name: str,
    start: Position,
    goal_name: str,
    goal: Position,
    preset: str,
    distance_m: float,
) -> SavedRoute:
    session.execute(
        delete(SavedRoute).where(
            SavedRoute.user_id == user_id,
            same_route(SavedRoute, start, goal, preset),
        )
    )
    if count_saved_routes(session, user_id) >= max_routes:
        raise SavedRoutesFullError(f"경로는 {max_routes}개까지 저장할 수 있습니다.")
    row = SavedRoute(
        user_id=user_id,
        start_name=start_name,
        start_lon=start[0],
        start_lat=start[1],
        goal_name=goal_name,
        goal_lon=goal[0],
        goal_lat=goal[1],
        preset=preset,
        distance_m=distance_m,
    )
    session.add(row)
    session.flush()
    return row


def count_saved_routes(session: Session, user_id: int) -> int:
    return session.scalar(select(func.count()).where(SavedRoute.user_id == user_id))


def list_saved_routes(session: Session, user_id: int) -> list[SavedRoute]:
    rows = session.scalars(
        select(SavedRoute)
        .where(SavedRoute.user_id == user_id)
        .order_by(SavedRoute.created_at.desc(), SavedRoute.id.desc())
    )
    return list(rows)


def delete_saved_route(session: Session, user_id: int, route_id: int) -> bool:
    """경로 하나를 지운다. 다른 사용자의 경로면 지우지 않고 False."""
    result = session.execute(
        delete(SavedRoute).where(
            SavedRoute.id == route_id, SavedRoute.user_id == user_id
        )
    )
    return result.rowcount > 0
