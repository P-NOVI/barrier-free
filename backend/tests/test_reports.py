from collections.abc import Iterator
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
FAR_AWAY = {"lon": 127.5, "lat": 37.0}
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture
def photo_dir(tmp_path: Path) -> Path:
    return tmp_path / "photos"


@pytest.fixture
def client(
    db_session: Session, sample_graph: Graph, photo_dir: Path
) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, report_photo_dir=photo_dir, report_photo_max_bytes=1000
    )
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_graph] = lambda: sample_graph
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def post_report(
    client: TestClient,
    photo: bytes | None = JPEG,
    kind: str = "curb",
    **fields: object,
):
    data = {"kind": kind, **ON_ROAD, **fields}
    files = {"photo": ("a.jpg", photo, "image/jpeg")} if photo is not None else None
    return client.post("/api/reports", data=data, files=files)


def test_report_is_saved_as_pending(
    client: TestClient, db_session: Session, photo_dir: Path
) -> None:
    response = post_report(client, kind="obstacle")

    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "obstacle"
    assert body["status"] == "pending"
    assert body["blocked"] is False
    assert "photo" not in " ".join(body)
    report = db_session.scalars(select(Report)).one()
    assert report.edge_id is not None
    assert report.user_id is not None
    # 사용자가 보낸 파일 이름이 아니라 만든 이름으로 저장한다.
    assert (photo_dir / report.photo_name).read_bytes() == JPEG
    assert report.photo_name.endswith(".jpg")
    assert (report.expires_at - report.created_at).days == EXPIRY_DAYS["obstacle"]


def test_description_is_saved_trimmed(client: TestClient, db_session: Session) -> None:
    response = post_report(client, description="  인도 턱이 높아요  ")

    assert response.status_code == 201
    assert response.json()["description"] == "인도 턱이 높아요"
    assert db_session.scalars(select(Report)).one().description == "인도 턱이 높아요"


@pytest.mark.parametrize("fields", [{}, {"description": "   "}])
def test_description_is_optional(
    client: TestClient, db_session: Session, fields: dict[str, str]
) -> None:
    response = post_report(client, **fields)

    assert response.status_code == 201
    assert response.json()["description"] is None
    assert db_session.scalars(select(Report)).one().description is None


def test_long_description_is_rejected(
    client: TestClient, db_session: Session, photo_dir: Path
) -> None:
    response = post_report(client, description="가" * 201)

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "description_too_long"
    assert db_session.scalars(select(Report)).all() == []
    assert not photo_dir.exists()


def test_report_requires_photo(client: TestClient, db_session: Session) -> None:
    response = post_report(client, photo=None)

    assert response.status_code == 422
    assert db_session.scalars(select(Report)).all() == []


def test_png_is_accepted(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/api/reports",
        data={"kind": "damage", **ON_ROAD},
        files={"photo": ("a.png", PNG, "image/png")},
    )

    assert response.status_code == 201
    assert db_session.scalars(select(Report)).one().photo_name.endswith(".png")


def test_non_image_is_rejected(
    client: TestClient, db_session: Session, photo_dir: Path
) -> None:
    response = post_report(client, photo=b"<script>alert(1)</script>")

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "bad_photo"
    assert db_session.scalars(select(Report)).all() == []
    assert not photo_dir.exists()


def test_large_photo_is_rejected(client: TestClient, db_session: Session) -> None:
    response = post_report(client, photo=JPEG + b"0" * 2000)

    assert response.status_code == 413
    assert response.json()["detail"]["reason"] == "photo_too_large"
    assert db_session.scalars(select(Report)).all() == []


def test_unknown_kind_is_rejected(client: TestClient) -> None:
    response = post_report(client, kind="alien")

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "unknown_kind"


def test_blocked_construction_is_saved(client: TestClient, db_session: Session) -> None:
    response = post_report(client, kind="construction", blocked="true")

    assert response.status_code == 201
    assert response.json()["blocked"] is True
    assert db_session.scalars(select(Report)).one().blocked is True


def test_blocked_is_only_for_construction(
    client: TestClient, db_session: Session
) -> None:
    response = post_report(client, kind="curb", blocked="true")

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "blocked_not_construction"
    assert db_session.scalars(select(Report)).all() == []


def test_report_far_from_roads_is_rejected(
    client: TestClient, db_session: Session, photo_dir: Path
) -> None:
    response = post_report(client, **FAR_AWAY)

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "off_network"
    assert db_session.scalars(select(Report)).all() == []
    assert not photo_dir.exists()


def test_coordinates_are_validated(client: TestClient) -> None:
    response = post_report(client, lon="500")

    assert response.status_code == 422
