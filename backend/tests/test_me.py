from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.deps import get_db_session
from app.main import app
from app.models import User

COOKIE = Settings(_env_file=None).auth_cookie_name
CITY_HALL = [126.9779, 37.5663]
SEOUL_STATION = [126.9707, 37.5547]
ROUTE = {
    "start_name": "서울시청",
    "start": CITY_HALL,
    "goal_name": "서울역",
    "goal": SEOUL_STATION,
    "preset": "manual_wheelchair",
    "distance_m": 1250.5,
}


@pytest.fixture
def new_client(db_session: Session) -> Iterator[Callable[[], TestClient]]:
    """같은 DB를 쓰는 브라우저. 부를 때마다 쿠키가 따로인 브라우저를 만든다."""
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    yield lambda: TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(new_client: Callable[[], TestClient]) -> TestClient:
    return new_client()


def user_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(User))


def test_session_issues_guest_cookie(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/session")

    assert response.status_code == 200
    assert response.json() == {"is_guest": True, "providers": [], "preset": "general"}
    set_cookie = response.headers["set-cookie"].lower()
    assert set_cookie.startswith(f"{COOKIE}=")
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert user_count(db_session) == 1


def test_session_reuses_cookie(client: TestClient, db_session: Session) -> None:
    client.post("/api/session")
    response = client.post("/api/session")

    assert response.status_code == 200
    # 계속 쓰는 동안 만료되지 않도록 쿠키를 다시 준다.
    assert COOKIE in response.headers["set-cookie"]
    assert user_count(db_session) == 1


def test_unknown_cookie_gets_new_guest(client: TestClient, db_session: Session) -> None:
    client.cookies.set(COOKIE, "wrong")

    response = client.post("/api/session")

    assert response.status_code == 200
    assert response.cookies[COOKIE] != "wrong"
    assert user_count(db_session) == 1


def test_reading_without_cookie_creates_nobody(
    client: TestClient, db_session: Session
) -> None:
    assert client.get("/api/session").json() == {
        "is_guest": True,
        "providers": [],
        "preset": "general",
    }
    assert client.get("/api/me/searches").json() == {"searches": []}
    assert client.get("/api/me/routes").json() == {"routes": []}
    assert user_count(db_session) == 0


def test_first_search_creates_guest(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/api/me/searches",
        json={
            "query": "서울역",
            "place_name": "서울역",
            "address": "서울 용산구 동자동",
            "position": SEOUL_STATION,
        },
    )

    assert response.status_code == 201
    assert COOKIE in client.cookies
    searches = client.get("/api/me/searches").json()["searches"]
    assert [(s["query"], s["position"]) for s in searches] == [
        ("서울역", SEOUL_STATION)
    ]
    assert user_count(db_session) == 1


def test_search_without_place(client: TestClient) -> None:
    response = client.post("/api/me/searches", json={"query": "시청"})

    assert response.status_code == 201
    body = response.json()
    assert body["place_name"] is None
    assert body["position"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"query": ""},
        {"query": "가" * 101},
        {"query": "시청", "position": [200, 37.5]},
    ],
)
def test_invalid_search_is_422(client: TestClient, body: dict) -> None:
    assert client.post("/api/me/searches", json=body).status_code == 422


def test_route_history_round_trip(client: TestClient) -> None:
    response = client.post("/api/me/routes", json=ROUTE)

    assert response.status_code == 201
    routes = client.get("/api/me/routes").json()["routes"]
    assert len(routes) == 1
    saved = routes[0]
    assert {key: saved[key] for key in ROUTE} == ROUTE
    assert saved["id"] == response.json()["id"]


def test_unknown_preset_route_is_422(client: TestClient) -> None:
    response = client.post("/api/me/routes", json={**ROUTE, "preset": "rocket"})

    assert response.status_code == 422


def test_histories_are_per_browser(new_client: Callable[[], TestClient]) -> None:
    first, second = new_client(), new_client()
    first.post("/api/me/searches", json={"query": "시청"})

    assert second.get("/api/me/searches").json() == {"searches": []}


def test_delete_own_entry(client: TestClient) -> None:
    entry_id = client.post("/api/me/searches", json={"query": "시청"}).json()["id"]

    assert client.delete(f"/api/me/searches/{entry_id}").status_code == 204
    assert client.delete(f"/api/me/searches/{entry_id}").status_code == 404
    assert client.get("/api/me/searches").json() == {"searches": []}


def test_cannot_delete_others_entry(new_client: Callable[[], TestClient]) -> None:
    owner, other = new_client(), new_client()
    entry_id = owner.post("/api/me/routes", json=ROUTE).json()["id"]
    other.post("/api/session")

    response = other.delete(f"/api/me/routes/{entry_id}")

    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "history_not_found"
    assert len(owner.get("/api/me/routes").json()["routes"]) == 1


def test_clear_histories(client: TestClient) -> None:
    client.post("/api/me/searches", json={"query": "시청"})
    client.post("/api/me/routes", json=ROUTE)

    assert client.delete("/api/me/searches").status_code == 204
    assert client.delete("/api/me/routes").status_code == 204
    assert client.get("/api/me/searches").json() == {"searches": []}
    assert client.get("/api/me/routes").json() == {"routes": []}


def test_clear_without_cookie_is_204(client: TestClient) -> None:
    assert client.delete("/api/me/searches").status_code == 204


def test_save_preset(client: TestClient) -> None:
    response = client.put("/api/me/preset", json={"preset": "stroller"})

    assert response.status_code == 200
    assert response.json() == {
        "is_guest": True,
        "providers": [],
        "preset": "stroller",
    }
    assert client.post("/api/session").json()["preset"] == "stroller"


def test_unknown_preset_is_422(client: TestClient) -> None:
    assert client.put("/api/me/preset", json={"preset": "rocket"}).status_code == 422


def test_unreachable_db_is_503(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'none' / 'app.db'}"
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url=database_url
    )
    try:
        response = TestClient(app).post("/api/session")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "db_unavailable"
