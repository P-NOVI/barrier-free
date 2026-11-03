import math
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_entrances, get_graph, get_sites
from app.main import app
from core.entrance import build_entrance_index
from core.graph import Graph, build_graph
from core.profiles import PRESETS
from core.site import build_site_index
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


def bends(a: list[float], b: list[float], c: list[float]) -> bool:
    """a → b → c 가 b 에서 방향을 바꾸는지"""
    cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
    return abs(cross) > 1e-12


@pytest.mark.usefixtures("use_graph")
def test_route_turns_where_it_changes_road(sample_graph: Graph) -> None:
    # 격자는 모서리 말고 모든 교차점이 갈림길이라, 방향을 바꾸는 곳마다 안내한다.
    response = client.post(
        "/api/route",
        json={
            "start": coordinate(sample_graph, 0),
            "goal": coordinate(sample_graph, 55),
        },
    )

    assert response.status_code == 200
    body = response.json()
    points = body["coordinates"]
    corners = [
        i
        for i in range(1, len(points) - 1)
        if bends(points[i - 1], points[i], points[i + 1])
    ]
    assert corners
    assert [turn["index"] for turn in body["turns"]] == corners
    for turn in body["turns"]:
        assert abs(turn["angle"]) == pytest.approx(90, abs=1)


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
@pytest.mark.parametrize("preset", PRESETS)
def test_duration_is_distance_at_preset_speed(sample_graph: Graph, preset: str) -> None:
    response = client.post(
        "/api/route",
        json={
            "start": coordinate(sample_graph, 0),
            "goal": coordinate(sample_graph, len(sample_graph.nodes) - 1),
            "preset": preset,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["duration_s"] == pytest.approx(
        body["distance_m"] / PRESETS[preset].speed_mps
    )


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


EAST_M_PER_DEGREE = 111_195.0 * math.cos(math.radians(37.5))


def meters(x: float, y: float) -> list[float]:
    """(127.0, 37.5) 에서 동쪽 x m, 북쪽 y m 인 좌표"""
    return [127.0 + x / EAST_M_PER_DEGREE, 37.5 + y / 111_195.0]


def flat_graph(points: list[list[float]], roads: list[tuple[int, int, float]]) -> Graph:
    """평지 길 (u, v, 길이) 로 이은 그래프"""
    return build_graph(
        {
            "nodes": [
                {"lon": lon, "lat": lat, "elevation": 0.0} for lon, lat in points
            ],
            "edges": [
                {
                    "id": i,
                    "u": u,
                    "v": v,
                    "length": length,
                    "grade": 0.0,
                    "steps": False,
                    "wheelchair_ok": True,
                    "walk_ok": True,
                }
                for i, (u, v, length) in enumerate(roads)
            ],
        }
    )


def post_route(graph: Graph, start: list[float], goal: list[float]) -> dict:
    app.dependency_overrides[get_graph] = lambda: graph
    try:
        response = client.post("/api/route", json={"start": start, "goal": goal})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    return response.json()


def test_goal_beside_long_road_is_reached_along_it() -> None:
    # 도착은 긴 길 P-Q 가운데에서 3m 옆이고, 가장 가까운 노드는 다른 길 끝 R(19m)이다.
    # 노드에 붙이면 P → T → R 로 돌아가고, 길에 붙이면 P-Q 를 따라 100m 간다.
    #   T ───────── R
    #   │
    #   P ───────── × ───────── Q   (× = 도착)
    p, q, t, r = meters(0, 0), meters(200, 0), meters(0, 22), meters(100, 22)
    graph = flat_graph([p, q, t, r], [(0, 1, 200.0), (0, 2, 22.0), (2, 3, 100.0)])

    body = post_route(graph, p, meters(100, 3))

    assert body["distance_m"] == pytest.approx(100, abs=0.5)
    assert body["coordinates"][0] == pytest.approx(p)
    assert body["coordinates"][-1] == pytest.approx(meters(100, 0), abs=1e-6)
    assert body["goal_gap_m"] == pytest.approx(3, abs=0.1)
    assert body["turns"] == []


def test_nearest_road_with_long_detour_is_skipped() -> None:
    # 출발은 막다른 길 D-E 에서 5m, 큰길 P-Q 에서 20m 다.
    # D-E 로 가면 E → U → V → Q 로 875m 돌아가므로, 큰길에서 300m 가는 쪽을 고른다.
    #       U ─────────────── V
    #       │                 │
    #   D ─ E                 │
    #     ×  (출발)            │
    #     P ───────────────── Q (도착)
    p, q = meters(0, 0), meters(300, 0)
    d, e, u, v = meters(-50, 25), meters(50, 25), meters(50, 300), meters(300, 300)
    graph = flat_graph(
        [p, q, d, e, u, v],
        [(0, 1, 300.0), (2, 3, 100.0), (3, 4, 275.0), (4, 5, 250.0), (5, 1, 300.0)],
    )

    body = post_route(graph, meters(0, 20), q)

    assert body["distance_m"] == pytest.approx(300, abs=0.5)
    assert body["start_gap_m"] == pytest.approx(20, abs=0.1)
    assert body["coordinates"][0] == pytest.approx(p, abs=1e-6)


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


def building_graph() -> tuple[Graph, dict]:
    """건물 가운데(0, 0) 북쪽 40m 에 뒷길, 남쪽 70m 에 앞길, 남쪽 벽(0, -55)에 출입구.

    두 길에서 도착(×)까지 거리는 같다. 출입구가 없으면 가까운 뒷길에서 시작한다.
         ───────────────┐ 뒷길 (북 40m)
        ┌─────┐         │
        │  ●  │         × 도착
        └──┬──┘         │
           출입구        │
         ───────────────┘ 앞길 (남 70m)
    """
    points = [meters(-100, 40), meters(100, 40), meters(-100, -70), meters(100, -70)]
    graph = flat_graph(points, [(0, 1, 200.0), (2, 3, 200.0), (3, 1, 110.0)])
    area = {
        "rings": [[meters(-30, -55), meters(30, -55), meters(30, 20), meters(-30, 20)]],
        "entrances": [{"lon": meters(0, -55)[0], "lat": meters(0, -55)[1]}],
    }
    area["rings"][0].append(area["rings"][0][0])
    return graph, area


def post_route_with_entrances(
    graph: Graph, areas: list[dict], start: list[float], goal: list[float], **extra
) -> dict:
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_entrances] = lambda: build_entrance_index(
        {"areas": areas}
    )
    try:
        response = client.post(
            "/api/route", json={"start": start, "goal": goal, **extra}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    return response.json()


def test_start_inside_building_leaves_by_its_entrance() -> None:
    graph, area = building_graph()
    goal = meters(100, -15)

    without = post_route_with_entrances(graph, [], meters(0, 0), goal)
    body = post_route_with_entrances(graph, [area], meters(0, 0), goal)

    assert without["coordinates"][0] == pytest.approx(meters(0, 40), abs=1e-6)
    assert without["start_entrance"] is None
    assert body["coordinates"][0] == pytest.approx(meters(0, -70), abs=1e-6)
    assert body["start_entrance"] == pytest.approx(meters(0, -55))
    assert body["start_gap_m"] == pytest.approx(15, abs=0.1)
    assert body["goal_entrance"] is None


def test_goal_inside_building_is_reached_at_its_entrance() -> None:
    graph, area = building_graph()

    body = post_route_with_entrances(graph, [area], meters(100, -15), meters(0, 0))

    assert body["coordinates"][-1] == pytest.approx(meters(0, -70), abs=1e-6)
    assert body["goal_entrance"] == pytest.approx(meters(0, -55))


def test_wheelchair_does_not_use_entrance_marked_no() -> None:
    graph, area = building_graph()
    area["entrances"][0]["wheelchair"] = "no"

    body = post_route_with_entrances(
        graph, [area], meters(0, 0), meters(100, -15), preset="manual_wheelchair"
    )

    assert body["start_entrance"] is None
    assert body["coordinates"][0] == pytest.approx(meters(0, 40), abs=1e-6)


def post_route_with_sites(
    graph: Graph, sites: list[dict], start: list[float], goal: list[float]
) -> dict:
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_sites] = lambda: build_site_index({"sites": sites})
    try:
        response = client.post("/api/route", json={"start": start, "goal": goal})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    return response.json()


def test_goal_outside_site_is_not_reached_over_its_wall() -> None:
    """도착(0, 0)은 캠퍼스 밖이다. 캠퍼스 안 길(북 50m)이 가깝고 경로도 짧다.

    시설을 모르면 캠퍼스 안 길에서 끝나 점선이 담장을 넘는다.
    0 ───────── 캠퍼스 안 길 ───────── 1   (북 50m)
    │      ┌ 캠퍼스 담장 (북 20m) ┐
    │                         × 도착
    2 ─────────── 바깥 길 ───────────── 3   (남 70m)
    """
    points = [meters(-300, 50), meters(0, 50), meters(-300, -70), meters(100, -70)]
    graph = flat_graph(points, [(0, 1, 300.0), (0, 2, 120.0), (2, 3, 400.0)])
    ring = [meters(-400, 20), meters(100, 20), meters(100, 200), meters(-400, 200)]
    campus = {"rings": [[*ring, ring[0]]]}

    without = post_route_with_sites(graph, [], points[0], meters(0, 0))
    body = post_route_with_sites(graph, [campus], points[0], meters(0, 0))

    assert without["coordinates"][-1] == pytest.approx(meters(0, 50), abs=1e-6)
    assert body["coordinates"][-1] == pytest.approx(meters(0, -70), abs=1e-6)
    assert body["goal_gap_m"] == pytest.approx(70, abs=0.1)


def square_ring(west: float, south: float, east: float, north: float) -> dict:
    ring = [meters(west, south), meters(east, south), meters(east, north)]
    ring += [meters(west, north), meters(west, south)]
    return {"rings": [ring]}


def test_goal_between_sites_never_ends_inside_neighbor_site() -> None:
    """도착(0, 0)은 길이 없는 단지 안이다. 서쪽은 캠퍼스, 동쪽은 학교다.

    서쪽 캠퍼스 안 길(80m)은 담장을 넘어야 닿고 경로도 짧다. 동쪽 바깥 길(130m)로
    가는 점선은 학교를 가로지르지만, 학교를 돌아서 갈 수 있어 이쪽에서 끝낸다.
    0 ────────────────────────────── 2   (북 200m)
    │ ┌캠퍼스┐ ┌단지┐ ┌학교┐ │
    │         ×도착
    1                                3   (남 200m)
    서 80m                          동 130m
    """
    points = [meters(-80, 200), meters(-80, -200), meters(130, 200), meters(130, -200)]
    graph = flat_graph(points, [(0, 1, 400.0), (0, 2, 210.0), (2, 3, 400.0)])
    sites = [
        square_ring(-400, -300, -50, 150),
        square_ring(-30, -30, 30, 30),
        square_ring(40, -100, 100, 100),
    ]

    without = post_route_with_sites(graph, [], points[0], meters(0, 0))
    body = post_route_with_sites(graph, sites, points[0], meters(0, 0))

    assert without["coordinates"][-1] == pytest.approx(meters(-80, 0), abs=1e-6)
    assert body["coordinates"][-1] == pytest.approx(meters(130, 0), abs=1e-6)
    assert body["goal_gap_m"] == pytest.approx(130, abs=0.1)
