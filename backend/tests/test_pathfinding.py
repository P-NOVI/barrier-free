from dataclasses import replace
from itertools import pairwise

from core.cost import is_passable
from core.graph import Graph, build_graph
from core.pathfinding import find_path
from core.profiles import PRESETS, CongestionTolerance


def make_graph(node_count: int, edges: list[dict]) -> Graph:
    nodes = [
        {"lon": 126.97 + i * 0.001, "lat": 37.56, "elevation": 0.0}
        for i in range(node_count)
    ]
    return build_graph({"nodes": nodes, "edges": edges})


def edge(
    edge_id: int, u: int, v: int, length: float, grade: float = 0.0, **flags: bool
) -> dict:
    return {
        "id": edge_id,
        "u": u,
        "v": v,
        "length": length,
        "grade": grade,
        "steps": flags.get("steps", False),
        "wheelchair_ok": flags.get("wheelchair_ok", not flags.get("steps", False)),
        "walk_ok": flags.get("walk_ok", True),
    }


# 0 → 3 으로 가는 두 갈래: 위쪽(0-1-3)은 짧은 계단, 아래쪽(0-2-3)은 긴 평지
STAIRS_OR_DETOUR = [
    edge(0, 0, 1, 50, 0.3, steps=True),
    edge(1, 1, 3, 50),
    edge(2, 0, 2, 100),
    edge(3, 2, 3, 100),
]


def test_wheelchair_avoids_stairs() -> None:
    graph = make_graph(4, STAIRS_OR_DETOUR)
    path = find_path(graph, 0, 3, PRESETS["manual_wheelchair"])
    assert path is not None
    assert path.nodes == [0, 2, 3]


def test_general_takes_shorter_stairs() -> None:
    graph = make_graph(4, STAIRS_OR_DETOUR)
    path = find_path(graph, 0, 3, PRESETS["general"])
    assert path is not None
    assert path.nodes == [0, 1, 3]


def test_grade_over_limit_is_avoided() -> None:
    graph = make_graph(
        4,
        [
            edge(0, 0, 1, 50, 0.1),
            edge(1, 1, 3, 50, -0.1),
            edge(2, 0, 2, 200),
            edge(3, 2, 3, 200),
        ],
    )
    manual = find_path(graph, 0, 3, PRESETS["manual_wheelchair"])
    power = find_path(graph, 0, 3, PRESETS["power_wheelchair"])
    assert manual is not None and manual.nodes == [0, 2, 3]
    assert power is not None and power.nodes == [0, 1, 3]


def test_no_path_when_only_stairs_connect() -> None:
    graph = make_graph(2, [edge(0, 0, 1, 50, 0.3, steps=True)])
    assert find_path(graph, 0, 1, PRESETS["manual_wheelchair"]) is None


def test_stairs_direction() -> None:
    graph = make_graph(2, [edge(0, 0, 1, 50, 0.3, steps=True)])
    down_only = replace(PRESETS["general"], stairs_up=False)
    assert find_path(graph, 0, 1, down_only) is None
    assert find_path(graph, 1, 0, down_only) is not None


def test_same_start_and_goal() -> None:
    graph = make_graph(2, [edge(0, 0, 1, 50)])
    path = find_path(graph, 1, 1, PRESETS["general"])
    assert path is not None
    assert path.nodes == [1] and path.arcs == [] and path.cost == 0


def test_congestion_avoided_by_avoid_tolerance() -> None:
    graph = make_graph(
        4,
        [
            edge(0, 0, 1, 100),
            edge(1, 1, 3, 100),
            edge(2, 0, 2, 110),
            edge(3, 2, 3, 110),
        ],
    )
    congestion = {0: 1.0, 1: 1.0}
    avoid = replace(PRESETS["general"], congestion_tolerance=CongestionTolerance.AVOID)
    ignore = replace(
        PRESETS["general"], congestion_tolerance=CongestionTolerance.IGNORE
    )
    avoid_path = find_path(graph, 0, 3, avoid, congestion)
    ignore_path = find_path(graph, 0, 3, ignore, congestion)
    assert avoid_path is not None and avoid_path.nodes == [0, 2, 3]
    assert ignore_path is not None and ignore_path.nodes == [0, 1, 3]


def test_sample_grid_paths_are_connected_and_passable(sample_graph: Graph) -> None:
    goal = len(sample_graph.nodes) - 1
    for name, profile in PRESETS.items():
        path = find_path(sample_graph, 0, goal, profile)
        assert path is not None, name
        assert path.nodes[0] == 0 and path.nodes[-1] == goal
        for arc, (u, v) in zip(path.arcs, pairwise(path.nodes), strict=True):
            assert (arc.source, arc.target) == (u, v)
            assert is_passable(arc, profile)
