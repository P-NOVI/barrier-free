import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import deps
from app.db import create_tables
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
    create_tables(engine)
    with Session(engine) as session:
        yield session
