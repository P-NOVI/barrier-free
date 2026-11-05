from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.deps import get_db_session, get_graph
from app.main import app
from app.models import Report
from app.services.report_service import EXPIRY_DAYS
from core.graph import Graph

# 샘플 격자의 첫 노드 근처
ON_ROAD = {"lon": 126.9779, "lat": 37.5663}
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


@pytest.fixture
def photo_dir(tmp_path: Path) -> Path:
    return tmp_path / "photos"


@pytest.fixture
def new_client(
    db_session: Session, sample_graph: Graph, photo_dir: Path
) -> Iterator[Callable[[], TestClient]]:
    """같은 DB를 쓰는 브라우저. 부를 때마다 쿠키가 따로인 브라우저를 만든다."""
    settings = Settings(
        _env_file=None, report_photo_dir=photo_dir, report_photo_max_bytes=1000
    )
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_graph] = lambda: sample_graph
    app.dependency_overrides[get_settings] = lambda: settings
    yield lambda: TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(new_client: Callable[[], TestClient]) -> TestClient:
    return new_client()


def post_report(client: TestClient, kind: str = "curb", **fields: object) -> dict:
    response = client.post(
        "/api/reports",
        data={"kind": kind, **ON_ROAD, **fields},
        files={"photo": ("a.jpg", JPEG, "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()


def my_reports(client: TestClient) -> list[dict]:
    return client.get("/api/me/reports").json()["reports"]


def test_no_cookie_gives_empty_list(client: TestClient) -> None:
    assert my_reports(client) == []


def test_guest_sees_own_reports_newest_first(client: TestClient) -> None:
    first = post_report(client, kind="curb")
    second = post_report(client, kind="damage")

    reports = my_reports(client)

    assert [report["id"] for report in reports] == [second["id"], first["id"]]
    assert "photo_name" not in reports[0]


def test_reports_are_per_browser(new_client: Callable[[], TestClient]) -> None:
    mine, other = new_client(), new_client()
    post_report(mine)
    post_report(other)

    assert len(my_reports(mine)) == 1
    assert len(my_reports(other)) == 1


def test_update_changes_description_and_kind(
    client: TestClient, db_session: Session
) -> None:
    report = post_report(client, kind="curb")

    response = client.patch(
        f"/api/me/reports/{report['id']}",
        json={"kind": "obstacle", "description": "  상자가 있어요  "},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "obstacle"
    assert body["description"] == "상자가 있어요"
    row = db_session.scalars(select(Report)).one()
    assert (row.expires_at - row.created_at).days == EXPIRY_DAYS["obstacle"]


def test_update_keeps_fields_that_are_not_sent(client: TestClient) -> None:
    report = post_report(client, kind="construction", blocked=True, description="공사")

    response = client.patch(
        f"/api/me/reports/{report['id']}", json={"description": "공사 중"}
    )

    body = response.json()
    assert body["kind"] == "construction"
    assert body["blocked"] is True
    assert body["description"] == "공사 중"


def test_update_with_empty_description_clears_it(client: TestClient) -> None:
    report = post_report(client, description="지워질 설명")

    response = client.patch(f"/api/me/reports/{report['id']}", json={"description": ""})

    assert response.json()["description"] is None


def test_update_rejects_blocked_for_non_construction(client: TestClient) -> None:
    report = post_report(client, kind="curb")

    response = client.patch(f"/api/me/reports/{report['id']}", json={"blocked": True})

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "blocked_not_construction"


def test_update_rejects_unknown_kind(client: TestClient) -> None:
    report = post_report(client)

    response = client.patch(f"/api/me/reports/{report['id']}", json={"kind": "x"})

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "unknown_kind"


@pytest.mark.parametrize("review_status", ["approved", "rejected"])
def test_update_is_refused_after_review(
    client: TestClient, db_session: Session, review_status: str
) -> None:
    report = post_report(client)
    db_session.scalars(select(Report)).one().status = review_status
    db_session.commit()

    response = client.patch(
        f"/api/me/reports/{report['id']}", json={"description": "바꾸기"}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "report_not_editable"


def test_update_of_others_report_is_404(
    new_client: Callable[[], TestClient],
) -> None:
    mine, other = new_client(), new_client()
    report = post_report(mine)
    post_report(other)

    response = other.patch(f"/api/me/reports/{report['id']}", json={"kind": "damage"})

    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "report_not_found"


def test_update_without_cookie_is_404(client: TestClient) -> None:
    response = client.patch("/api/me/reports/1", json={"kind": "damage"})

    assert response.status_code == 404


def test_delete_removes_report_and_photo(
    client: TestClient, db_session: Session, photo_dir: Path
) -> None:
    report = post_report(client)
    photo = photo_dir / db_session.scalars(select(Report)).one().photo_name
    assert photo.exists()

    response = client.delete(f"/api/me/reports/{report['id']}")

    assert response.status_code == 204
    assert my_reports(client) == []
    assert not photo.exists()


def test_delete_works_after_review(client: TestClient, db_session: Session) -> None:
    report = post_report(client)
    db_session.scalars(select(Report)).one().status = "approved"
    db_session.commit()

    assert client.delete(f"/api/me/reports/{report['id']}").status_code == 204


def test_delete_when_photo_is_already_gone(
    client: TestClient, db_session: Session, photo_dir: Path
) -> None:
    report = post_report(client)
    (photo_dir / db_session.scalars(select(Report)).one().photo_name).unlink()

    assert client.delete(f"/api/me/reports/{report['id']}").status_code == 204


def test_delete_of_others_report_is_404(
    new_client: Callable[[], TestClient], db_session: Session
) -> None:
    mine, other = new_client(), new_client()
    report = post_report(mine)
    post_report(other)

    response = other.delete(f"/api/me/reports/{report['id']}")

    assert response.status_code == 404
    assert len(my_reports(mine)) == 1


def test_delete_missing_or_without_cookie_is_404(client: TestClient) -> None:
    assert client.delete("/api/me/reports/999").status_code == 404
