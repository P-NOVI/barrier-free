import math
from dataclasses import replace

import pytest

from core.graph import Graph, build_graph
from core.profiles import PRESETS
from core.reachability import (
    EndpointFailure,
    Endpoints,
    component_labels,
    pick_endpoints,
)

ORIGIN = (126.9779, 37.5663)
M_PER_DEG_LAT = 111_195.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(ORIGIN[1]))
WHEELCHAIR = PRESETS["manual_wheelchair"]
GENERAL = PRESETS["general"]


def at(east_m: float, north_m: float) -> tuple[float, float]:
    return ORIGIN[0] + east_m / M_PER_DEG_LON, ORIGIN[1] + north_m / M_PER_DEG_LAT


def make_graph(points: list[tuple[float, float]], edges: list[dict]) -> Graph:
    nodes = [{"lon": lon, "lat": lat, "elevation": 0.0} for lon, lat in points]
    return build_graph({"nodes": nodes, "edges": edges})


def edge(edge_id: int, u: int, v: int, length: float, *, steps: bool = False):
    return {
        "id": edge_id,
        "u": u,
        "v": v,
        "length": length,
        "grade": 0.3 if steps else 0.0,
        "steps": steps,
        "wheelchair_ok": not steps,
        "walk_ok": True,
    }


# A(0) 는 계단으로만 C(1) 와 이어진다. C(1) - B(2) - G(3) 는 평지.
#   C
#   |계단
#   A  B ---------- G
POINTS = [at(0, 0), at(0, 60), at(30, 0), at(180, 0)]
A, C, B, G = range(4)
EDGES = [
    edge(0, A, C, 60, steps=True),
    edge(1, C, B, 70),
    edge(2, B, G, 150),
]


def test_component_labels_split_by_stairs_for_wheelchair() -> None:
    graph = make_graph(POINTS, EDGES)
    wheelchair = component_labels(graph, WHEELCHAIR)
    general = component_labels(graph, GENERAL)

    assert wheelchair[A] != wheelchair[C]
    assert wheelchair[C] == wheelchair[B] == wheelchair[G]
    assert len(set(general)) == 1


def test_one_way_stairs_still_connect() -> None:
    graph = make_graph(POINTS, EDGES)
    down_only = replace(GENERAL, stairs_up=False)
    labels = component_labels(graph, down_only)
    assert labels[A] == labels[C]


def test_component_labels_are_cached() -> None:
    graph = make_graph(POINTS, EDGES)
    assert component_labels(graph, WHEELCHAIR) is component_labels(graph, WHEELCHAIR)


def test_wheelchair_start_moves_off_isolated_node() -> None:
    graph = make_graph(POINTS, EDGES)
    picked = pick_endpoints(graph, POINTS[A], POINTS[G], WHEELCHAIR, 200)

    assert isinstance(picked, Endpoints)
    assert (picked.start, picked.goal) == (B, G)
    assert picked.start_gap_m == pytest.approx(30, abs=0.5)
    assert picked.goal_gap_m == 0


def test_general_uses_nearest_nodes() -> None:
    graph = make_graph(POINTS, EDGES)
    picked = pick_endpoints(graph, POINTS[A], POINTS[G], GENERAL, 200)

    assert isinstance(picked, Endpoints)
    assert (picked.start, picked.goal) == (A, G)


def test_close_points_do_not_collapse_into_one_node() -> None:
    # 계단 아래·위 두 노드뿐이면 휠체어는 같은 노드로 모이지 않고 경로 없음
    graph = make_graph(POINTS[:2], [EDGES[0]])
    picked = pick_endpoints(graph, POINTS[A], POINTS[C], WHEELCHAIR, 200)
    assert picked is EndpointFailure.NOT_CONNECTED


def test_not_connected_when_clusters_join_only_by_stairs() -> None:
    points = [at(0, 0), at(30, 0), at(1000, 0), at(1030, 0)]
    graph = make_graph(
        points,
        [edge(0, 0, 1, 30), edge(1, 1, 2, 970, steps=True), edge(2, 2, 3, 30)],
    )

    assert (
        pick_endpoints(graph, points[0], points[3], WHEELCHAIR, 200)
        is EndpointFailure.NOT_CONNECTED
    )
    assert isinstance(
        pick_endpoints(graph, points[0], points[3], GENERAL, 200), Endpoints
    )


def test_off_network() -> None:
    graph = make_graph(POINTS, EDGES)
    far = at(5000, 0)
    assert (
        pick_endpoints(graph, far, POINTS[G], GENERAL, 200)
        is EndpointFailure.START_OFF_NETWORK
    )
    assert (
        pick_endpoints(graph, POINTS[A], far, GENERAL, 200)
        is EndpointFailure.GOAL_OFF_NETWORK
    )
