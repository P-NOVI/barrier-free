"""즐겨찾기와 내 장소. 함수는 commit 하지 않는다.

같은 위치의 즐겨찾기, 같은 이름의 내 장소는 하나만 둔다. 다시 저장하면 예전 것을 지운다.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import SavedPlace

Position = tuple[float, float]


class PlacesFullError(Exception):
    """사용자가 저장할 수 있는 장소 수를 넘었다."""


def add_place(
    session: Session,
    user_id: int,
    max_places: int,
    kind: str,
    label: str | None,
    name: str,
    address: str | None,
    position: Position,
) -> SavedPlace:
    lon, lat = position
    same = (
        SavedPlace.label == label
        if kind == "mine"
        else (SavedPlace.lon == lon) & (SavedPlace.lat == lat)
    )
    session.execute(
        delete(SavedPlace).where(
            SavedPlace.user_id == user_id, SavedPlace.kind == kind, same
        )
    )
    if count_places(session, user_id) >= max_places:
        raise PlacesFullError(f"장소는 {max_places}개까지 저장할 수 있습니다.")
    row = SavedPlace(
        user_id=user_id,
        kind=kind,
        label=label,
        name=name,
        address=address,
        lon=lon,
        lat=lat,
    )
    session.add(row)
    session.flush()
    return row


def count_places(session: Session, user_id: int) -> int:
    return session.scalar(select(func.count()).where(SavedPlace.user_id == user_id))


def list_places(session: Session, user_id: int) -> list[SavedPlace]:
    rows = session.scalars(
        select(SavedPlace)
        .where(SavedPlace.user_id == user_id)
        .order_by(SavedPlace.created_at.desc(), SavedPlace.id.desc())
    )
    return list(rows)


def delete_place(session: Session, user_id: int, place_id: int) -> bool:
    """장소 하나를 지운다. 다른 사용자의 장소면 지우지 않고 False."""
    result = session.execute(
        delete(SavedPlace).where(
            SavedPlace.id == place_id, SavedPlace.user_id == user_id
        )
    )
    return result.rowcount > 0
