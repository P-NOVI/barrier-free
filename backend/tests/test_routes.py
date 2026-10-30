from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_graph
from app.main import app
from core.graph import Graph, build_graph
from core.slope import MODERATE_MAX_GRADE

client = TestClient(app)


@pytest.fixture
def use_graph(sample_graph: Graph) -> Iterator[None]:
    app.dependency_overrides[get_graph] = lambda: sample_graph
    yield
    app.dependency_overrides.clear()


def coordinate(graph: Graph, node: int) -> list[float]:
    return [graph.nodes[node].lon, graph.nodes[node].lat]


@pytest.mark.usefixtures("use_graph")
def test_route_between_grid_corners(sample_graph: Graph) -> None:
    goal = len(sample_graph.nodes) - 1
    response = client.post(
        "/api/route",
        json={
            "start": coordinate(sample_graph, 0),
            "goal": coordinate(sample_graph, goal),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["coordinates"][0] == coordinate(sample_graph, 0)
    assert body["coordinates"][-1] == coordinate(sample_graph, goal)
    assert len(body["coordinates"]) == len(body["elevations"])
    assert len(body["coordinates"]) == len(body["distances_m"])
    assert body["distances_m"][0] == 0
    assert body["distances_m"][-1] == pytest.approx(body["distance_m"])


@pytest.mark.usefixtures("use_graph")
def test_wheelchair_route_has_no_steps_or_steep_grade(sample_graph: Graph) -> None:
    response = client.post(
        "/api/route",
        json={
            "start": coordinate(sample_graph, 0),
            "goal": coordinate(sample_graph, len(sample_graph.nodes) - 1),
            "preset": "manual_wheelchair",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["steps_count"] == 0
    assert body["max_grade"] <= MODERATE_MAX_GRADE


@pytest.mark.usefixtures("use_graph")
def test_unknown_preset_is_rejected(sample_graph: Graph) -> None:
    response = client.post(
        "/api/route",
        json={
            "start": coordinate(sample_graph, 0),
            "goal": coordinate(sample_graph, 1),
            "preset": "bicycle",
        },
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("use_graph")
def test_start_far_from_network(sample_graph: Graph) -> None:
    response = client.post(
        "/api/route",
        json={"start": [127.5, 37.0], "goal": coordinate(sample_graph, 1)},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "start_off_network"


def test_no_path_for_wheelchair_over_stairs_only() -> None:
    graph = build_graph(
        {
            "nodes": [
                {"lon": 126.9779, "lat": 37.5663, "elevation": 30.0},
                {"lon": 126.9780, "lat": 37.5663, "elevation": 33.0},
            ],
            "edges": [
                {
                    "id": 0,
                    "u": 0,
                    "v": 1,
                    "length": 10.0,
                    "grade": 0.3,
                    "steps": True,
                    "wheelchair_ok": False,
                    "walk_ok": True,
                }
            ],
        }
    )
    app.dependency_overrides[get_graph] = lambda: graph
    try:
        response = client.post(
            "/api/route",
            json={
                "start": coordinate(graph, 0),
                "goal": coordinate(graph, 1),
                "preset": "manual_wheelchair",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "no_path"


def test_route_follows_road_shape() -> None:
    # 두 노드 사이 길에 중간 지점이 둘 있고, 모양은 1 → 0 순서로 저장돼 있다.
    graph = build_graph(
        {
            "nodes": [
                {"lon": 126.990, "lat": 37.534, "elevation": 30.0},
                {"lon": 126.993, "lat": 37.534, "elevation": 33.0},
            ],
            "edges": [
                {
                    "id": 0,
                    "u": 1,
                    "v": 0,
                    "length": 300.0,
                    "grade": -0.01,
                    "steps": False,
                    "wheelchair_ok": True,
                    "walk_ok": True,
                    "geometry": [[126.992, 37.534], [126.991, 37.534]],
                }
            ],
        }
    )
    app.dependency_overrides[get_graph] = lambda: graph
    try:
        response = client.post(
            "/api/route",
            json={"start": coordinate(graph, 0), "goal": coordinate(graph, 1)},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["coordinates"] == [
        [126.990, 37.534],
        [126.991, 37.534],
        [126.992, 37.534],
        [126.993, 37.534],
    ]
    # 중간 지점의 고도·거리는 양 끝 값을 지나온 비율로 나눈다
    assert body["elevations"] == pytest.approx([30.0, 31.0, 32.0, 33.0])
    assert body["distances_m"] == pytest.approx([0.0, 100.0, 200.0, 300.0])
    assert body["distance_m"] == 300.0


def test_missing_graph_file(tmp_path: Path) -> None:
    missing = Settings(graph_path=tmp_path / "graph.json.gz")
    app.dependency_overrides[get_settings] = lambda: missing
    try:
        response = client.post(
            "/api/route", json={"start": [126.9779, 37.5663], "goal": [126.98, 37.57]}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "graph_unavailable"
