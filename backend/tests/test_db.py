from fastapi.testclient import TestClient
from httpx import Response

from app.config import Settings, get_settings
from app.main import app

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
