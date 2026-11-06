"""검색 이력과 경로 이력. 함수는 commit 하지 않는다.

같은 검색·경로를 다시 하면 예전 것을 지우고 맨 앞에 새로 넣는다.
사용자마다 최근 keep 개만 남긴다.
"""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import RouteHistory, SearchHistory

Position = tuple[float, float]
History = type[SearchHistory] | type[RouteHistory]


def add_search(
    session: Session,
    user_id: int,
    keep: int,
    query: str,
    place_name: str | None = None,
    address: str | None = None,
    position: Position | None = None,
) -> SearchHistory:
    lon, lat = position if position else (None, None)
    row = SearchHistory(
        query=query, place_name=place_name, address=address, lon=lon, lat=lat
    )
    return _add(session, user_id, keep, row, query=query, place_name=place_name)


def add_route(
    session: Session,
    user_id: int,
    keep: int,
    start_name: str,
    start: Position,
    goal_name: str,
    goal: Position,
    preset: str,
    distance_m: float,
) -> RouteHistory:
    same_route = {
        "start_lon": start[0],
        "start_lat": start[1],
        "goal_lon": goal[0],
        "goal_lat": goal[1],
        "preset": preset,
    }
    row = RouteHistory(
        start_name=start_name, goal_name=goal_name, distance_m=distance_m, **same_route
    )
    return _add(session, user_id, keep, row, **same_route)


def list_searches(session: Session, user_id: int, limit: int) -> list[SearchHistory]:
    return _list(session, SearchHistory, user_id, limit)


def list_routes(session: Session, user_id: int, limit: int) -> list[RouteHistory]:
    return _list(session, RouteHistory, user_id, limit)


def delete_entry(session: Session, model: History, user_id: int, entry_id: int) -> bool:
    """이력 하나를 지운다. 다른 사용자의 이력이면 지우지 않고 False."""
    result = session.execute(
        delete(model).where(model.id == entry_id, model.user_id == user_id)
    )
    return result.rowcount > 0


def clear(session: Session, model: History, user_id: int) -> None:
    session.execute(delete(model).where(model.user_id == user_id))


def _add[Row: (SearchHistory, RouteHistory)](
    session: Session, user_id: int, keep: int, row: Row, **same: Any
) -> Row:
    model = type(row)
    session.execute(
        delete(model).where(
            model.user_id == user_id,
            # 장소를 고르지 않은 검색(None)끼리도 같은 것으로 본다.
            *(
                getattr(model, column).is_not_distinct_from(value)
                for column, value in same.items()
            ),
        )
    )
    row.user_id = user_id
    session.add(row)
    session.flush()
    kept = select(model.id).where(model.user_id == user_id)
    kept = kept.order_by(model.created_at.desc(), model.id.desc()).limit(keep)
    session.execute(
        delete(model).where(model.user_id == user_id, model.id.not_in(kept))
    )
    return row


def _list[Row: (SearchHistory, RouteHistory)](
    session: Session, model: type[Row], user_id: int, limit: int
) -> list[Row]:
    rows = session.scalars(
        select(model)
        .where(model.user_id == user_id)
        .order_by(model.created_at.desc(), model.id.desc())
        .limit(limit)
    )
    return list(rows)
