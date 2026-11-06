import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  모델을 불러와야 Base.metadata 에 테이블이 등록된다.
from app import deps
from app.config import get_settings
from app.db import Base
from app.migrate import alembic_config
from core.entrance import NO_ENTRANCES
from core.graph import Graph, build_graph
from core.site import NO_SITES

SAMPLE_GRAPH = Path(__file__).resolve().parents[2] / "data" / "sample" / "graph.json"


@pytest.fixture(autouse=True)
def no_real_entrances(monkeypatch: pytest.MonkeyPatch) -> None:
    """data/processed/entrances.json.gz 의 실제 건물이 테스트 좌표에 걸리지 않게 한다.

    출입구를 쓰는 테스트는 get_entrances 를 따로 덮어쓴다.
    """
    monkeypatch.setattr(deps, "load_entrances", lambda path: NO_ENTRANCES)
    monkeypatch.setattr(deps, "load_sites", lambda path: NO_SITES)


@pytest.fixture(autouse=True)
def no_real_sdot_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """backend/.env 의 S-DoT 키를 비워, 경로 요청이 실제 API를 부르지 않게 한다.

    혼잡도를 쓰는 테스트는 get_road_congestion 을 따로 덮어쓴다.
    """
    monkeypatch.setenv("SDOT_API_KEY", "")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def no_real_photo_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """backend/.env 의 Supabase 키를 비워, 제보 사진이 실제 버킷에 올라가지 않게 한다.

    키가 없으면 사진은 설정의 report_photo_dir 폴더에 저장된다.
    Supabase 를 쓰는 테스트는 설정을 직접 만들고 transport 를 넘긴다.
    """
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def no_real_closed_roads(monkeypatch: pytest.MonkeyPatch) -> None:
    """backend/.env 의 DB에서 막힌 길을 읽지 않게 한다.

    막힌 길을 쓰는 테스트는 get_closed_edges 를 따로 덮어쓴다.
    """
    monkeypatch.setattr(deps, "closed_edge_ids", lambda session, now: frozenset())
    deps.get_closed_road_cache().entry = None


@pytest.fixture(autouse=True)
def no_real_route_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    """backend/.env 의 DB에서 경로가 지나는 제보를 읽지 않게 한다.

    제보를 쓰는 테스트는 get_report_finder 를 따로 덮어쓴다.
    """
    monkeypatch.setattr(deps, "list_reviewable_reports", lambda *args: [])


@pytest.fixture(scope="session")
def sample_graph() -> Graph:
    return build_graph(json.loads(SAMPLE_GRAPH.read_text(encoding="utf-8")))


@pytest.fixture
def db_session() -> Iterator[Session]:
    # 메모리 DB는 연결마다 따로 생기므로 연결 하나를 계속 쓴다.
    # API 테스트에서는 FastAPI 가 다른 스레드에서 이 연결을 쓴다.
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # 마이그레이션이 모델과 같은지는 test_migrations 가 본다. 여기서는 모델로 만든다.
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def migrate() -> Callable[[Engine, str], None]:
    """.env 의 주소 대신 넘긴 엔진에 마지막 마이그레이션까지 적용한다."""

    def upgrade(engine: Engine, name: str) -> None:
        config = alembic_config(name)
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    return upgrade
