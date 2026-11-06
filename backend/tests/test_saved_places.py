from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.deps import get_db_session
from app.main import app
from app.models import User
from app.repositories.place_repository import add_place, list_places
from app.repositories.user_repository import create_guest, sign_in_with_social

CITY_HALL = [126.9779, 37.5663]
SEOUL_STATION = [126.9707, 37.5547]
FAVORITE = {"kind": "favorite", "name": "서울시청", "position": CITY_HALL}
HOME = {
    "kind": "mine",
    "label": "집",
    "name": "서울역",
    "address": "서울 용산구 한강대로 405",
    "position": SEOUL_STATION,
}
MAX_PLACES = 3


@pytest.fixture
def new_client(db_session: Session) -> Iterator[Callable[[], TestClient]]:
    """같은 DB를 쓰는 브라우저. 부를 때마다 쿠키가 따로인 브라우저를 만든다."""
    settings = Settings(_env_file=None, saved_places_max=MAX_PLACES)
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: settings
    yield lambda: TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(new_client: Callable[[], TestClient]) -> TestClient:
    return new_client()


def places(client: TestClient) -> list[dict]:
    return client.get("/api/me/places").json()["places"]


def test_reading_without_cookie_creates_nobody(
    client: TestClient, db_session: Session
) -> None:
    assert places(client) == []
    assert db_session.scalar(select(func.count()).select_from(User)) == 0


def test_save_and_list_places(client: TestClient) -> None:
    favorite = client.post("/api/me/places", json=FAVORITE)
    home = client.post("/api/me/places", json=HOME)

    assert favorite.status_code == 201
    assert home.status_code == 201
    assert favorite.json()["label"] is None
    assert favorite.json()["address"] is None
    saved = places(client)
    # 최근 것부터
    assert [place["id"] for place in saved] == [
        home.json()["id"],
        favorite.json()["id"],
    ]
    assert saved[0] | {"id": 0, "created_at": ""} == HOME | {
        "id": 0,
        "created_at": "",
    }


def test_same_favorite_position_is_saved_once(client: TestClient) -> None:
    client.post("/api/me/places", json=FAVORITE)
    client.post("/api/me/places", json=FAVORITE | {"name": "시청"})

    assert [place["name"] for place in places(client)] == ["시청"]


def test_same_label_replaces_my_place(client: TestClient) -> None:
    client.post("/api/me/places", json=HOME)
    client.post("/api/me/places", json=HOME | {"name": "시청", "position": CITY_HALL})
    client.post("/api/me/places", json=HOME | {"label": "회사"})

    saved = {place["label"]: place["name"] for place in places(client)}
    assert saved == {"집": "시청", "회사": "서울역"}


@pytest.mark.parametrize(
    "body",
    [
        HOME | {"label": None},
        FAVORITE | {"label": "집"},
        HOME | {"label": ""},
        HOME | {"label": "가" * 21},
        FAVORITE | {"name": ""},
        FAVORITE | {"kind": "other"},
        FAVORITE | {"position": [200, 37.5]},
    ],
)
def test_invalid_place_is_422(client: TestClient, body: dict) -> None:
    assert client.post("/api/me/places", json=body).status_code == 422


def test_too_many_places_is_409(client: TestClient) -> None:
    for label in ("집", "회사", "학교"):
        client.post("/api/me/places", json=HOME | {"label": label})

    response = client.post("/api/me/places", json=FAVORITE)
    # 이미 있는 이름은 바꿔 저장하므로 가득 차도 된다.
    replaced = client.post("/api/me/places", json=HOME | {"name": "새 집"})

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "places_full"
    assert replaced.status_code == 201
    assert len(places(client)) == MAX_PLACES


def test_places_are_per_browser(new_client: Callable[[], TestClient]) -> None:
    first, second = new_client(), new_client()
    first.post("/api/me/places", json=FAVORITE)

    assert places(second) == []


def test_cannot_delete_others_place(new_client: Callable[[], TestClient]) -> None:
    owner, other = new_client(), new_client()
    place_id = owner.post("/api/me/places", json=FAVORITE).json()["id"]
    other.post("/api/session")

    response = other.delete(f"/api/me/places/{place_id}")

    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "place_not_found"
    assert owner.delete(f"/api/me/places/{place_id}").status_code == 204
    assert places(owner) == []


def test_member_takes_over_guest_places(db_session: Session) -> None:
    member_id, _ = sign_in_with_social(db_session, None, "kakao", "k1", None)
    add_place(db_session, member_id, 10, "mine", "집", "회원 집", None, CITY_HALL)
    guest, _ = create_guest(db_session)
    add_place(db_session, guest.id, 10, "mine", "집", "게스트 집", None, SEOUL_STATION)
    add_place(db_session, guest.id, 10, "mine", "회사", "회사", None, SEOUL_STATION)
    add_place(db_session, guest.id, 10, "favorite", None, "시청", None, CITY_HALL)

    sign_in_with_social(db_session, guest.id, "kakao", "k1", None)

    saved = {
        (row.kind, row.label, row.name) for row in list_places(db_session, member_id)
    }
    # 같은 이름의 내 장소는 회원 것을 남긴다.
    assert saved == {
        ("mine", "집", "회원 집"),
        ("mine", "회사", "회사"),
        ("favorite", None, "시청"),
    }
