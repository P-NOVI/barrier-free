from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import deps
from app.config import Settings
from app.db import Base
from app.deps import get_closed_edges, get_graph
from app.main import app
from app.models import Report, utc_now
from app.repositories import closure_repository
from app.repositories.closure_repository import APPROVED, closed_edge_ids
from app.services.congestion_service import TtlCache
from core.closure import close_edges
from core.graph import Graph, build_graph
from core.pathfinding import find_path
from core.profiles import PRESETS

client = TestClient(app)

# 0 ─(0)─ 1 바로 가는 길과, 2·3 을 거쳐 돌아가는 길이 있다.
#  \(2)    \(3)
#   2 ─(1)─ 3
DIRECT_M = 89.0
DETOUR_M = 56.0 + 89.0 + 56.0


def two_way_graph() -> Graph:
    def edge(edge_id: int, u: int, v: int, length: float) -> dict:
        return {
            "id": edge_id,
            "u": u,
            "v": v,
            "length": length,
            "grade": 0.0,
            "steps": False,
            "wheelchair_ok": True,
            "walk_ok": True,
        }

    return build_graph(
        {
            "nodes": [
                {"lon": 126.990, "lat": 37.5340, "elevation": 0.0},
                {"lon": 126.991, "lat": 37.5340, "elevation": 0.0},
                {"lon": 126.990, "lat": 37.5345, "elevation": 0.0},
                {"lon": 126.991, "lat": 37.5345, "elevation": 0.0},
            ],
            "edges": [
                edge(0, 0, 1, DIRECT_M),
                edge(1, 2, 3, 89.0),
                edge(2, 0, 2, 56.0),
                edge(3, 1, 3, 56.0),
            ],
        }
    )


def edge_ids(graph: Graph, start: int, goal: int) -> list[int]:
    path = find_path(graph, start, goal, PRESETS["general"])
    assert path is not None
    return [arc.edge_id for arc in path.arcs]


def test_closed_edge_is_avoided() -> None:
    graph = two_way_graph()

    closed = close_edges(graph, frozenset({0}))

    assert edge_ids(closed, 0, 1) == [2, 1, 3]
    # 원래 그래프는 그대로다.
    assert edge_ids(graph, 0, 1) == [0]


def test_closed_edge_blocks_every_profile() -> None:
    closed = close_edges(two_way_graph(), frozenset({0, 1}))

    for profile in PRESETS.values():
        assert find_path(closed, 0, 1, profile) is None


def test_no_closed_edges_keeps_graph() -> None:
    graph = two_way_graph()

    assert close_edges(graph, frozenset()) is graph


def test_same_closed_edges_reuse_graph() -> None:
    graph = two_way_graph()

    assert close_edges(graph, frozenset({0})) is close_edges(graph, frozenset({0}))
    assert close_edges(graph, frozenset({0})) is not close_edges(graph, frozenset({1}))


@pytest.fixture
def route_graph() -> Iterator[Graph]:
    graph = two_way_graph()
    app.dependency_overrides[get_graph] = lambda: graph
    yield graph
    app.dependency_overrides.clear()


def coordinate(graph: Graph, node: int) -> list[float]:
    return [graph.nodes[node].lon, graph.nodes[node].lat]


def route_distance(graph: Graph) -> float:
    response = client.post(
        "/api/route",
        json={"start": coordinate(graph, 0), "goal": coordinate(graph, 1)},
    )
    assert response.status_code == 200
    return response.json()["distance_m"]


def test_route_goes_around_closed_road(route_graph: Graph) -> None:
    assert route_distance(route_graph) == pytest.approx(DIRECT_M)

    app.dependency_overrides[get_closed_edges] = lambda: frozenset({0})

    assert route_distance(route_graph) == pytest.approx(DETOUR_M)


def test_route_fails_when_every_road_is_closed(route_graph: Graph) -> None:
    app.dependency_overrides[get_closed_edges] = lambda: frozenset({0, 1, 2, 3})

    response = client.post(
        "/api/route",
        json={"start": coordinate(route_graph, 0), "goal": coordinate(route_graph, 1)},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "no_path"


def add_report(
    session: Session, edge_id: int, status: str, blocked: bool, expires_in_days: int
) -> None:
    now = utc_now()
    session.add(
        Report(
            kind="construction",
            blocked=blocked,
            status=status,
            photo_name=f"{edge_id}.jpg",
            lon=126.99,
            lat=37.534,
            edge_id=edge_id,
            created_at=now,
            expires_at=now + timedelta(days=expires_in_days),
        )
    )


def test_closed_edge_ids_keep_only_approved_blocked_live_reports(
    db_session: Session,
) -> None:
    add_report(db_session, 10, APPROVED, blocked=True, expires_in_days=3)
    add_report(db_session, 11, APPROVED, blocked=True, expires_in_days=-1)
    add_report(db_session, 12, "pending", blocked=True, expires_in_days=3)
    add_report(db_session, 13, APPROVED, blocked=False, expires_in_days=3)
    add_report(db_session, 14, "rejected", blocked=True, expires_in_days=3)
    db_session.commit()

    assert closed_edge_ids(db_session, utc_now()) == frozenset({10})


def test_get_closed_edges_without_database_url() -> None:
    settings = Settings(_env_file=None, database_url="")

    assert get_closed_edges(settings, TtlCache(60)) == frozenset()


def test_get_closed_edges_reads_db_once_per_ttl(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(deps, "closed_edge_ids", closure_repository.closed_edge_ids)
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        add_report(session, 7, APPROVED, blocked=True, expires_in_days=3)
        session.commit()
    settings = Settings(_env_file=None, database_url=database_url)
    cache: TtlCache[frozenset[int]] = TtlCache(60)

    assert get_closed_edges(settings, cache) == frozenset({7})

    with Session(engine) as session:
        add_report(session, 8, APPROVED, blocked=True, expires_in_days=3)
        session.commit()
    # 캐시 시간 안에는 DB를 다시 읽지 않는다.
    assert get_closed_edges(settings, cache) == frozenset({7})


def test_get_closed_edges_ignores_unreachable_db(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setattr(deps, "closed_edge_ids", closure_repository.closed_edge_ids)
    # 없는 폴더 안의 파일은 열 수 없어 접속 오류가 난다.
    database_url = f"sqlite:///{tmp_path / 'none' / 'app.db'}"
    settings = Settings(_env_file=None, database_url=database_url)
    cache: TtlCache[frozenset[int]] = TtlCache(60)

    assert get_closed_edges(settings, cache) == frozenset()
    assert "막힌 길을 읽지 못해" in caplog.text
    assert cache.get() == frozenset()
