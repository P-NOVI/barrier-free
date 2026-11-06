from datetime import UTC, datetime

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.main import app, prepare_database
from app.migrate import APP_DB
from app.models import User

client = TestClient(app)


def get_health_db(database_url: str) -> Response:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url=database_url
    )
    try:
        return client.get("/health/db")
    finally:
        app.dependency_overrides.clear()


def test_health_db_ok() -> None:
    response = get_health_db("sqlite://")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_database_url_is_503() -> None:
    response = get_health_db("")

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "db_unavailable"


def test_unreachable_db_is_503(tmp_path) -> None:
    # 없는 폴더 안의 파일은 열 수 없어 접속 오류가 난다.
    response = get_health_db(f"sqlite:///{tmp_path / 'none' / 'app.db'}")

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "db_unavailable"


def test_prepare_database_warns_when_not_migrated(tmp_path, caplog) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"

    prepare_database(Settings(_env_file=None, database_url=database_url))

    assert "alembic upgrade head" in caplog.text
    assert inspect(create_engine(database_url)).get_table_names() == []


def test_prepare_database_purges_old_guests_after_migration(
    tmp_path, caplog, migrate
) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    engine = create_engine(database_url)
    migrate(engine, APP_DB)
    with Session(engine) as session:
        session.add(User(last_seen_at=datetime(2000, 1, 1, tzinfo=UTC)))
        session.commit()

    prepare_database(Settings(_env_file=None, database_url=database_url))

    assert "alembic" not in caplog.text
    with Session(engine) as session:
        assert session.scalars(select(User)).all() == []


def test_prepare_database_skips_unreachable_db(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'none' / 'app.db'}"

    prepare_database(Settings(_env_file=None, database_url=database_url))
