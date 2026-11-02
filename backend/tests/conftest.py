import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import create_tables
from core.graph import Graph, build_graph

SAMPLE_GRAPH = Path(__file__).resolve().parents[2] / "data" / "sample" / "graph.json"


@pytest.fixture(scope="session")
def sample_graph() -> Graph:
    return build_graph(json.loads(SAMPLE_GRAPH.read_text(encoding="utf-8")))


@pytest.fixture
def db_session() -> Iterator[Session]:
    # 메모리 DB는 연결마다 따로 생기므로 연결 하나를 계속 쓴다.
    engine = create_engine("sqlite://", poolclass=StaticPool)
    create_tables(engine)
    with Session(engine) as session:
        yield session
