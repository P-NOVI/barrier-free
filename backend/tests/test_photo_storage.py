from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import main
from app.config import Settings, get_settings
from app.deps import get_db_session, get_graph, get_photo_storage
from app.main import app
from app.models import Report
from app.repositories.user_repository import sign_in_with_social
from app.services.photo_storage import (
    LocalPhotoStorage,
    PhotoStorageError,
    SupabasePhotoStorage,
    create_photo_storage,
    create_supabase_client,
)
from core.graph import Graph

ON_ROAD = {"lon": 126.9779, "lat": 37.5663}
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
SUPABASE = Settings(
    _env_file=None,
    supabase_url="http://supabase.test/",
    supabase_service_key="secret-key",
    supabase_photo_bucket="photos",
    admin_accounts="google:admin-sub",
)


def supabase_storage(
    handler: Callable[[httpx.Request], httpx.Response],
) -> SupabasePhotoStorage:
    client = create_supabase_client(SUPABASE, httpx.MockTransport(handler))
    return SupabasePhotoStorage(client, SUPABASE.supabase_photo_bucket)


def test_supabase_save_posts_the_photo_with_the_service_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"Key": "photos/a.jpg"})

    supabase_storage(handler).save("a.jpg", JPEG, "image/jpeg")

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == "http://supabase.test/storage/v1/object/photos/a.jpg"
    assert request.headers["authorization"] == "Bearer secret-key"
    assert request.headers["apikey"] == "secret-key"
    assert request.headers["content-type"] == "image/jpeg"
    assert request.content == JPEG


def test_supabase_read_uses_the_authenticated_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=JPEG)

    assert supabase_storage(handler).read("a.jpg") == JPEG
    assert seen[0].method == "GET"
    assert (
        str(seen[0].url)
        == "http://supabase.test/storage/v1/object/authenticated/photos/a.jpg"
    )


@pytest.mark.parametrize("code", [400, 404])
def test_supabase_read_missing_photo_is_none(code: int) -> None:
    storage = supabase_storage(lambda request: httpx.Response(code, json={}))

    assert storage.read("a.jpg") is None


def test_supabase_delete_sends_delete_and_ignores_missing() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404, json={})

    supabase_storage(handler).delete("a.jpg")

    assert seen[0].method == "DELETE"
    assert str(seen[0].url) == "http://supabase.test/storage/v1/object/photos/a.jpg"


@pytest.mark.parametrize("action", ["save", "read", "delete"])
def test_supabase_server_error_raises(action: str) -> None:
    storage = supabase_storage(lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(PhotoStorageError):
        if action == "save":
            storage.save("a.jpg", JPEG, "image/jpeg")
        elif action == "read":
            storage.read("a.jpg")
        else:
            storage.delete("a.jpg")


def test_supabase_network_error_hides_the_address_and_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url} with secret-key")

    with pytest.raises(PhotoStorageError) as error:
        supabase_storage(handler).read("a.jpg")

    assert "secret-key" not in str(error.value)
    assert "supabase.test" not in str(error.value)


def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalPhotoStorage(tmp_path / "photos")

    assert storage.read("a.jpg") is None
    storage.save("a.jpg", JPEG, "image/jpeg")
    assert storage.read("a.jpg") == JPEG
    storage.delete("a.jpg")
    storage.delete("a.jpg")
    assert storage.read("a.jpg") is None


def test_storage_is_local_without_a_supabase_key(tmp_path: Path) -> None:
    only_url = Settings(_env_file=None, supabase_url="http://supabase.test")
    only_key = Settings(_env_file=None, supabase_service_key="secret-key")

    for settings in (Settings(_env_file=None), only_url, only_key):
        storage, client = create_photo_storage(settings)

        assert isinstance(storage, LocalPhotoStorage)
        assert client is None


def test_storage_is_supabase_with_url_and_key() -> None:
    storage, client = create_photo_storage(SUPABASE)

    assert isinstance(storage, SupabasePhotoStorage)
    assert client is not None
    client.close()


class FakeStorage:
    def __init__(self) -> None:
        self.photos: dict[str, bytes] = {}
        self.fail = False

    def check(self) -> None:
        if self.fail:
            raise PhotoStorageError("down")

    def save(self, name: str, content: bytes, media_type: str) -> None:
        self.check()
        self.photos[name] = content

    def read(self, name: str) -> bytes | None:
        self.check()
        return self.photos.get(name)

    def delete(self, name: str) -> None:
        self.check()
        self.photos.pop(name, None)


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def new_client(
    db_session: Session, sample_graph: Graph, storage: FakeStorage
) -> Iterator[Callable[[], TestClient]]:
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_graph] = lambda: sample_graph
    app.dependency_overrides[get_settings] = lambda: SUPABASE
    app.dependency_overrides[get_photo_storage] = lambda: storage
    yield lambda: TestClient(app)
    app.dependency_overrides.clear()


def post_report(client: TestClient) -> httpx.Response:
    return client.post(
        "/api/reports",
        data={"kind": "curb", **ON_ROAD},
        files={"photo": ("a.jpg", JPEG, "image/jpeg")},
    )


def report_count(db_session: Session) -> int:
    return db_session.scalar(select(func.count()).select_from(Report)) or 0


def test_report_photo_goes_to_the_storage(
    new_client: Callable[[], TestClient], db_session: Session, storage: FakeStorage
) -> None:
    response = post_report(new_client())

    assert response.status_code == 201
    name = db_session.scalars(select(Report.photo_name)).one()
    assert storage.photos == {name: JPEG}


def test_report_is_not_created_when_the_photo_cannot_be_saved(
    new_client: Callable[[], TestClient], db_session: Session, storage: FakeStorage
) -> None:
    storage.fail = True

    response = post_report(new_client())

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "photo_storage_failed"
    assert report_count(db_session) == 0


def admin_client(
    new_client: Callable[[], TestClient], db_session: Session
) -> TestClient:
    client = new_client()
    _, token = sign_in_with_social(db_session, None, "google", "admin-sub", None)
    db_session.commit()
    client.cookies.set(SUPABASE.auth_cookie_name, token)
    return client


def test_admin_sees_the_photo_from_the_storage(
    new_client: Callable[[], TestClient], db_session: Session, storage: FakeStorage
) -> None:
    report_id = post_report(new_client()).json()["id"]

    response = admin_client(new_client, db_session).get(
        f"/api/admin/reports/{report_id}/photo"
    )

    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, no-store"


def test_admin_photo_missing_from_the_storage_is_404(
    new_client: Callable[[], TestClient], db_session: Session, storage: FakeStorage
) -> None:
    report_id = post_report(new_client()).json()["id"]
    storage.photos.clear()

    response = admin_client(new_client, db_session).get(
        f"/api/admin/reports/{report_id}/photo"
    )

    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "photo_not_found"


def test_admin_photo_is_502_when_the_storage_is_down(
    new_client: Callable[[], TestClient], db_session: Session, storage: FakeStorage
) -> None:
    report_id = post_report(new_client()).json()["id"]
    storage.fail = True

    response = admin_client(new_client, db_session).get(
        f"/api/admin/reports/{report_id}/photo"
    )

    assert response.status_code == 502
    assert response.json()["detail"]["reason"] == "photo_storage_failed"


def test_deleting_my_report_deletes_its_photo(
    new_client: Callable[[], TestClient], db_session: Session, storage: FakeStorage
) -> None:
    client = new_client()
    report_id = post_report(client).json()["id"]

    response = client.delete(f"/api/me/reports/{report_id}")

    assert response.status_code == 204
    assert storage.photos == {}


def test_deleting_my_report_succeeds_even_if_the_photo_stays(
    new_client: Callable[[], TestClient], db_session: Session, storage: FakeStorage
) -> None:
    client = new_client()
    report_id = post_report(client).json()["id"]
    storage.fail = True

    response = client.delete(f"/api/me/reports/{report_id}")

    assert response.status_code == 204
    assert report_count(db_session) == 0


def test_purge_keeps_deleting_when_one_photo_fails(
    monkeypatch: pytest.MonkeyPatch, storage: FakeStorage
) -> None:
    deleted: list[str] = []

    class Flaky(FakeStorage):
        def delete(self, name: str) -> None:
            if name == "a.jpg":
                raise PhotoStorageError("down")
            deleted.append(name)

    monkeypatch.setattr(main, "create_photo_storage", lambda settings: (Flaky(), None))

    main.delete_photos(SUPABASE, ["a.jpg", "b.jpg"])

    assert deleted == ["b.jpg"]
