from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.deps import get_db_session
from app.main import app
from app.models import User
from app.repositories.saved_route_repository import (
    add_saved_route,
    list_saved_routes,
)
from app.repositories.user_repository import create_guest, sign_in_with_social

CITY_HALL = [126.9779, 37.5663]
SEOUL_STATION = [126.9707, 37.5547]
DEOKSUGUNG = [126.9752, 37.5658]
ROUTE = {
    "start_name": "서울역",
    "start": SEOUL_STATION,
    "goal_name": "서울시청",
    "goal": CITY_HALL,
    "preset": "manual_wheelchair",
    "distance_m": 1520.5,
}
MAX_ROUTES = 2


@pytest.fixture
def new_client(db_session: Session) -> Iterator[Callable[[], TestClient]]:
    """같은 DB를 쓰는 브라우저. 부를 때마다 쿠키가 따로인 브라우저를 만든다."""
    settings = Settings(_env_file=None, saved_routes_max=MAX_ROUTES)
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: settings
    yield lambda: TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(new_client: Callable[[], TestClient]) -> TestClient:
    return new_client()


def saved_routes(client: TestClient) -> list[dict]:
    return client.get("/api/me/saved-routes").json()["routes"]


def test_reading_without_cookie_creates_nobody(
    client: TestClient, db_session: Session
) -> None:
    assert saved_routes(client) == []
    assert db_session.scalar(select(func.count()).select_from(User)) == 0


def test_save_and_list_routes(client: TestClient) -> None:
    first = client.post("/api/me/saved-routes", json=ROUTE)
    second = client.post(
        "/api/me/saved-routes", json=ROUTE | {"goal_name": "덕수궁", "goal": DEOKSUGUNG}
    )

    assert first.status_code == 201
    assert second.status_code == 201
    saved = saved_routes(client)
    # 최근 것부터
    assert [route["id"] for route in saved] == [
        second.json()["id"],
        first.json()["id"],
    ]
    assert saved[1] | {"id": 0, "created_at": ""} == ROUTE | {
        "id": 0,
        "created_at": "",
    }


def test_same_route_is_saved_once(client: TestClient) -> None:
    client.post("/api/me/saved-routes", json=ROUTE)
    client.post("/api/me/saved-routes", json=ROUTE | {"goal_name": "시청"})
    # 이동 조건이 다르면 다른 경로다.
    client.post("/api/me/saved-routes", json=ROUTE | {"preset": "general"})

    saved = {(route["goal_name"], route["preset"]) for route in saved_routes(client)}
    assert saved == {("시청", "manual_wheelchair"), ("서울시청", "general")}


@pytest.mark.parametrize(
    "body",
    [
        ROUTE | {"start_name": ""},
        ROUTE | {"preset": "rocket"},
        ROUTE | {"distance_m": -1},
        ROUTE | {"goal": [200, 37.5]},
    ],
)
def test_invalid_route_is_422(client: TestClient, body: dict) -> None:
    assert client.post("/api/me/saved-routes", json=body).status_code == 422


def test_too_many_routes_is_409(client: TestClient) -> None:
    client.post("/api/me/saved-routes", json=ROUTE)
    client.post("/api/me/saved-routes", json=ROUTE | {"goal": DEOKSUGUNG})

    response = client.post("/api/me/saved-routes", json=ROUTE | {"preset": "general"})
    # 이미 있는 경로는 바꿔 저장하므로 가득 차도 된다.
    replaced = client.post("/api/me/saved-routes", json=ROUTE | {"goal_name": "시청"})

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "saved_routes_full"
    assert replaced.status_code == 201
    assert len(saved_routes(client)) == MAX_ROUTES


def test_routes_are_per_browser(new_client: Callable[[], TestClient]) -> None:
    first, second = new_client(), new_client()
    first.post("/api/me/saved-routes", json=ROUTE)

    assert saved_routes(second) == []


def test_cannot_delete_others_route(new_client: Callable[[], TestClient]) -> None:
    owner, other = new_client(), new_client()
    route_id = owner.post("/api/me/saved-routes", json=ROUTE).json()["id"]
    other.post("/api/session")

    response = other.delete(f"/api/me/saved-routes/{route_id}")

    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "saved_route_not_found"
    assert owner.delete(f"/api/me/saved-routes/{route_id}").status_code == 204
    assert saved_routes(owner) == []


def test_member_takes_over_guest_routes(db_session: Session) -> None:
    station, hall, palace = (
        tuple(SEOUL_STATION),
        tuple(CITY_HALL),
        tuple(DEOKSUGUNG),
    )
    member_id, _ = sign_in_with_social(db_session, None, "kakao", "k1", None)
    add_saved_route(
        db_session, member_id, 10, "회원 출발", station, "시청", hall, "general", 1.0
    )
    guest, _ = create_guest(db_session)
    add_saved_route(
        db_session, guest.id, 10, "게스트 출발", station, "시청", hall, "general", 1.0
    )
    add_saved_route(
        db_session, guest.id, 10, "서울역", station, "덕수궁", palace, "general", 1.0
    )

    sign_in_with_social(db_session, guest.id, "kakao", "k1", None)

    saved = {
        (row.start_name, row.goal_name)
        for row in list_saved_routes(db_session, member_id)
    }
    # 같은 경로는 회원 것을 남긴다.
    assert saved == {("회원 출발", "시청"), ("서울역", "덕수궁")}
