from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.deps import get_db_session, get_graph
from app.main import app
from app.models import Report, utc_now
from app.repositories.user_repository import sign_in_with_social
from core.graph import Graph

ON_ROAD = {"lon": 126.9779, "lat": 37.5663}
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


@pytest.fixture
def photo_dir(tmp_path: Path) -> Path:
    return tmp_path / "photos"


@pytest.fixture
def settings(photo_dir: Path) -> Settings:
    return Settings(
        _env_file=None,
        report_photo_dir=photo_dir,
        report_photo_max_bytes=1000,
        admin_accounts="google:admin-sub, kakao:777",
    )


@pytest.fixture
def new_client(
    db_session: Session, sample_graph: Graph, settings: Settings
) -> Iterator[Callable[[], TestClient]]:
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_graph] = lambda: sample_graph
    app.dependency_overrides[get_settings] = lambda: settings
    yield lambda: TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def user_client(new_client: Callable[[], TestClient]) -> TestClient:
    return new_client()


def login(
    client: TestClient,
    db_session: Session,
    settings: Settings,
    provider: str,
    provider_user_id: str,
) -> None:
    _, token = sign_in_with_social(db_session, None, provider, provider_user_id, None)
    db_session.commit()
    client.cookies.set(settings.auth_cookie_name, token)


@pytest.fixture
def admin(
    new_client: Callable[[], TestClient], db_session: Session, settings: Settings
) -> TestClient:
    client = new_client()
    login(client, db_session, settings, "google", "admin-sub")
    return client


def post_report(client: TestClient, kind: str = "curb", **fields: object) -> dict:
    response = client.post(
        "/api/reports",
        data={"kind": kind, **ON_ROAD, **fields},
        files={"photo": ("a.jpg", JPEG, "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()


def test_no_cookie_is_401(user_client: TestClient) -> None:
    response = user_client.get("/api/admin/reports")

    assert response.status_code == 401


def test_guest_is_403(user_client: TestClient) -> None:
    post_report(user_client)

    response = user_client.get("/api/admin/reports")

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "admin_only"


def test_member_who_is_not_admin_is_403(
    new_client: Callable[[], TestClient], db_session: Session, settings: Settings
) -> None:
    client = new_client()
    login(client, db_session, settings, "google", "someone-else")

    assert client.get("/api/admin/reports").status_code == 403


def test_same_id_on_other_provider_is_not_admin(
    new_client: Callable[[], TestClient], db_session: Session, settings: Settings
) -> None:
    client = new_client()
    login(client, db_session, settings, "kakao", "admin-sub")

    assert client.get("/api/admin/reports").status_code == 403


def test_session_reports_is_admin(admin: TestClient, user_client: TestClient) -> None:
    assert admin.get("/api/session").json()["is_admin"] is True
    assert user_client.get("/api/session").json()["is_admin"] is False


def test_list_shows_pending_with_details_oldest_first(
    admin: TestClient, new_client: Callable[[], TestClient]
) -> None:
    first = post_report(
        new_client(), kind="construction", blocked=True, description="공사"
    )
    second = post_report(new_client(), kind="damage")

    reports = admin.get("/api/admin/reports").json()["reports"]

    assert [r["id"] for r in reports] == [first["id"], second["id"]]
    assert reports[0]["kind"] == "construction"
    assert reports[0]["blocked"] is True
    assert reports[0]["description"] == "공사"
    assert reports[0]["status"] == "pending"
    assert reports[0]["photo_url"] == f"/api/admin/reports/{first['id']}/photo"
    assert "photo_name" not in reports[0]
    assert "edge_id" not in reports[0]


def test_list_rejects_unknown_status(admin: TestClient) -> None:
    response = admin.get("/api/admin/reports", params={"report_status": "nope"})

    assert response.status_code == 422


def test_approve_moves_report_out_of_pending(
    admin: TestClient, user_client: TestClient, db_session: Session
) -> None:
    report = post_report(user_client)

    response = admin.post(f"/api/admin/reports/{report['id']}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert admin.get("/api/admin/reports").json()["reports"] == []
    approved = admin.get("/api/admin/reports", params={"report_status": "approved"})
    assert [r["id"] for r in approved.json()["reports"]] == [report["id"]]
    assert db_session.scalars(select(Report)).one().status == "approved"


def test_cancel_sets_rejected_status(
    admin: TestClient, user_client: TestClient
) -> None:
    report = post_report(user_client)

    response = admin.post(f"/api/admin/reports/{report['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_reviewed_report_cannot_be_reviewed_again(
    admin: TestClient, user_client: TestClient
) -> None:
    report = post_report(user_client)
    admin.post(f"/api/admin/reports/{report['id']}/approve")

    for action in ("approve", "cancel"):
        response = admin.post(f"/api/admin/reports/{report['id']}/{action}")
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "report_not_pending"


def test_owner_cannot_edit_after_review(
    admin: TestClient, user_client: TestClient
) -> None:
    report = post_report(user_client)
    admin.post(f"/api/admin/reports/{report['id']}/approve")

    response = user_client.patch(
        f"/api/me/reports/{report['id']}", json={"description": "고침"}
    )

    assert response.status_code == 409


def test_review_unknown_report_is_404(admin: TestClient) -> None:
    assert admin.post("/api/admin/reports/999/approve").status_code == 404
    assert admin.post("/api/admin/reports/999/cancel").status_code == 404


def test_non_admin_cannot_review(
    user_client: TestClient, new_client: Callable[[], TestClient], admin: TestClient
) -> None:
    report = post_report(user_client)

    response = user_client.post(f"/api/admin/reports/{report['id']}/approve")

    assert response.status_code == 403
    assert (
        new_client().post(f"/api/admin/reports/{report['id']}/cancel").status_code
        == 401
    )
    pending = admin.get("/api/admin/reports").json()["reports"]
    assert [r["id"] for r in pending] == [report["id"]]


def test_photo_is_served_to_admin_only(
    admin: TestClient, user_client: TestClient
) -> None:
    report = post_report(user_client)
    url = f"/api/admin/reports/{report['id']}/photo"

    response = admin.get(url)

    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert "no-store" in response.headers["cache-control"]
    assert user_client.get(url).status_code == 403


def test_photo_missing_file_is_404(
    admin: TestClient, user_client: TestClient, photo_dir: Path
) -> None:
    report = post_report(user_client)
    for file in photo_dir.iterdir():
        file.unlink()

    response = admin.get(f"/api/admin/reports/{report['id']}/photo")

    assert response.status_code == 404


def test_admin_accounts_parsing() -> None:
    parsed = Settings(
        _env_file=None, admin_accounts=" google:1 ,kakao:2,, bad ,:3, x: "
    ).admin_account_set

    assert parsed == {("google", "1"), ("kakao", "2")}
    assert Settings(_env_file=None).admin_account_set == frozenset()


def expire(db_session: Session, report_id: int, days_ago: int = 1) -> None:
    row = db_session.get(Report, report_id)
    assert row is not None
    row.expires_at = utc_now() - timedelta(days=days_ago)
    db_session.commit()


def test_expired_report_cannot_be_approved(
    admin: TestClient, user_client: TestClient, db_session: Session
) -> None:
    report = post_report(user_client)
    expire(db_session, report["id"])

    response = admin.post(f"/api/admin/reports/{report['id']}/approve")

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "report_expired"
    assert db_session.get(Report, report["id"]).status == "pending"


def test_expired_report_can_still_be_cancelled(
    admin: TestClient, user_client: TestClient, db_session: Session
) -> None:
    report = post_report(user_client)
    expire(db_session, report["id"])

    response = admin.post(f"/api/admin/reports/{report['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def approve(admin: TestClient, report_id: int) -> None:
    assert admin.post(f"/api/admin/reports/{report_id}/approve").status_code == 200


def test_resolve_moves_approved_report_to_resolved(
    admin: TestClient, user_client: TestClient
) -> None:
    report = post_report(user_client)
    approve(admin, report["id"])

    response = admin.post(f"/api/admin/reports/{report['id']}/resolve")

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    approved = admin.get("/api/admin/reports", params={"report_status": "approved"})
    assert approved.json()["reports"] == []
    resolved = admin.get("/api/admin/reports", params={"report_status": "resolved"})
    assert [r["id"] for r in resolved.json()["reports"]] == [report["id"]]


def test_only_approved_report_can_be_resolved(
    admin: TestClient, user_client: TestClient
) -> None:
    pending = post_report(user_client)
    cancelled = post_report(user_client)
    resolved = post_report(user_client)
    admin.post(f"/api/admin/reports/{cancelled['id']}/cancel")
    approve(admin, resolved["id"])
    admin.post(f"/api/admin/reports/{resolved['id']}/resolve")

    for report in (pending, cancelled, resolved):
        response = admin.post(f"/api/admin/reports/{report['id']}/resolve")
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "report_not_approved"


def test_expired_approved_report_can_be_resolved(
    admin: TestClient, user_client: TestClient, db_session: Session
) -> None:
    report = post_report(user_client)
    approve(admin, report["id"])
    expire(db_session, report["id"])

    response = admin.post(f"/api/admin/reports/{report['id']}/resolve")

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"


def test_resolved_report_cannot_be_reviewed_again(
    admin: TestClient, user_client: TestClient
) -> None:
    report = post_report(user_client)
    approve(admin, report["id"])
    admin.post(f"/api/admin/reports/{report['id']}/resolve")

    for action in ("approve", "cancel"):
        response = admin.post(f"/api/admin/reports/{report['id']}/{action}")
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "report_not_pending"


def test_owner_cannot_edit_resolved_report(
    admin: TestClient, user_client: TestClient
) -> None:
    report = post_report(user_client)
    approve(admin, report["id"])
    admin.post(f"/api/admin/reports/{report['id']}/resolve")

    response = user_client.patch(
        f"/api/me/reports/{report['id']}", json={"description": "고침"}
    )

    assert response.status_code == 409
    mine = user_client.get("/api/me/reports").json()["reports"]
    assert mine[0]["status"] == "resolved"


def test_resolve_unknown_report_is_404(admin: TestClient) -> None:
    assert admin.post("/api/admin/reports/999/resolve").status_code == 404


def test_only_admin_can_resolve(
    admin: TestClient,
    user_client: TestClient,
    new_client: Callable[[], TestClient],
) -> None:
    report = post_report(user_client)
    approve(admin, report["id"])
    url = f"/api/admin/reports/{report['id']}/resolve"

    assert user_client.post(url).status_code == 403
    assert new_client().post(url).status_code == 401
    approved = admin.get("/api/admin/reports", params={"report_status": "approved"})
    assert [r["id"] for r in approved.json()["reports"]] == [report["id"]]
