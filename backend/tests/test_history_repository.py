from sqlalchemy.orm import Session

from app.models import RouteHistory, SearchHistory
from app.repositories.history_repository import (
    add_route,
    add_search,
    clear,
    delete_entry,
    list_routes,
    list_searches,
)
from app.repositories.user_repository import create_guest

KEEP = 50
CITY_HALL = (126.9779, 37.5663)
SEOUL_STATION = (126.9707, 37.5547)


def queries(session: Session, user_id: int) -> list[str]:
    return [row.query for row in list_searches(session, user_id, KEEP)]


def test_searches_are_newest_first(db_session: Session) -> None:
    guest, _ = create_guest(db_session)

    add_search(db_session, guest.id, KEEP, "시청")
    add_search(
        db_session, guest.id, KEEP, "서울역", "서울역", "서울 용산구", SEOUL_STATION
    )

    rows = list_searches(db_session, guest.id, KEEP)
    assert [row.query for row in rows] == ["서울역", "시청"]
    assert (rows[0].lon, rows[0].lat) == SEOUL_STATION
    assert rows[1].place_name is None


def test_same_search_moves_to_front(db_session: Session) -> None:
    guest, _ = create_guest(db_session)

    add_search(db_session, guest.id, KEEP, "시청")
    add_search(db_session, guest.id, KEEP, "서울역")
    add_search(db_session, guest.id, KEEP, "시청")

    assert queries(db_session, guest.id) == ["시청", "서울역"]


def test_same_query_with_other_place_is_kept(db_session: Session) -> None:
    guest, _ = create_guest(db_session)

    add_search(db_session, guest.id, KEEP, "역", "서울역", "", SEOUL_STATION)
    add_search(db_session, guest.id, KEEP, "역", "시청역", "", CITY_HALL)

    assert len(list_searches(db_session, guest.id, KEEP)) == 2


def test_only_recent_entries_are_kept(db_session: Session) -> None:
    guest, _ = create_guest(db_session)

    for query in ["a", "b", "c", "d"]:
        add_search(db_session, guest.id, 3, query)

    assert queries(db_session, guest.id) == ["d", "c", "b"]


def test_histories_are_per_user(db_session: Session) -> None:
    first, _ = create_guest(db_session)
    second, _ = create_guest(db_session)

    add_search(db_session, first.id, KEEP, "시청")

    assert queries(db_session, second.id) == []


def test_same_route_moves_to_front(db_session: Session) -> None:
    guest, _ = create_guest(db_session)

    def go(start, goal, preset="general") -> None:
        add_route(
            db_session, guest.id, KEEP, "출발", start, "도착", goal, preset, 900.0
        )

    go(CITY_HALL, SEOUL_STATION)
    go(SEOUL_STATION, CITY_HALL)
    go(CITY_HALL, SEOUL_STATION, "manual_wheelchair")
    go(CITY_HALL, SEOUL_STATION)

    rows = list_routes(db_session, guest.id, KEEP)
    assert [(row.start_lon, row.preset) for row in rows] == [
        (CITY_HALL[0], "general"),
        (CITY_HALL[0], "manual_wheelchair"),
        (SEOUL_STATION[0], "general"),
    ]


def test_delete_entry_only_own(db_session: Session) -> None:
    owner, _ = create_guest(db_session)
    other, _ = create_guest(db_session)
    row = add_search(db_session, owner.id, KEEP, "시청")

    assert not delete_entry(db_session, SearchHistory, other.id, row.id)
    assert delete_entry(db_session, SearchHistory, owner.id, row.id)
    assert queries(db_session, owner.id) == []


def test_clear_removes_all_of_user(db_session: Session) -> None:
    guest, _ = create_guest(db_session)
    add_route(
        db_session,
        guest.id,
        KEEP,
        "시청",
        CITY_HALL,
        "서울역",
        SEOUL_STATION,
        "general",
        1200.0,
    )

    clear(db_session, RouteHistory, guest.id)

    assert list_routes(db_session, guest.id, KEEP) == []
