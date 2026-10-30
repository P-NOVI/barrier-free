import math

import pytest

from core.graph import Graph, build_graph
from core.pathfinding import find_path
from core.profiles import PRESETS
from core.road_point import nearby_road_points, with_road_points
from core.snap import METERS_PER_DEGREE

ORIGIN = (127.0, 37.5)
GENERAL = PRESETS["general"]


def at(x: float, y: float) -> tuple[float, float]:
    """원점에서 동쪽 x m, 북쪽 y m 인 좌표"""
    east = METERS_PER_DEGREE * math.cos(math.radians(ORIGIN[1]))
    return ORIGIN[0] + x / east, ORIGIN[1] + y / METERS_PER_DEGREE


def make_graph(
    points: list[tuple[float, float]],
    roads: list[tuple[int, int, float]],
    shapes: dict[int, list[tuple[float, float]]] | None = None,
) -> Graph:
    """points 는 m 좌표, roads 는 (u, v, 길이). shapes 는 길 번호 → 중간 지점(m)."""
    shapes = shapes or {}
    return build_graph(
        {
            "nodes": [
                {"lon": lon, "lat": lat, "elevation": 10.0 * i}
                for i, (lon, lat) in enumerate(at(*point) for point in points)
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
                    "geometry": [at(*point) for point in shapes.get(i, [])],
                }
                for i, (u, v, length) in enumerate(roads)
            ],
        }
    )


# P(0) ── 200m ── Q(1), P(0) ── 50m ── N(2)
LINE = make_graph([(0, 0), (200, 0), (0, 50)], [(0, 1, 200.0), (0, 2, 50.0)])


def test_nearby_road_points_are_nearest_first() -> None:
    points = nearby_road_points(LINE, *at(120, 8), 150)

    assert [point.edge.edge_id for point in points] == [0, 1]
    assert points[0].gap_m == pytest.approx(8, abs=0.1)
    assert points[0].share == pytest.approx(0.6, abs=0.001)
    assert points[1].gap_m == pytest.approx(math.hypot(120, 8), abs=0.5)
    assert nearby_road_points(LINE, *at(120, 80), 50) == []


def test_point_in_middle_splits_road() -> None:
    [point, *_] = nearby_road_points(LINE, *at(120, 8), 100)
    graph, [node] = with_road_points(LINE, [point])

    assert node == 3
    assert len(graph.nodes) == len(graph.adjacency) == 4
    assert (graph.nodes[node].lon, graph.nodes[node].lat) == pytest.approx(at(120, 0))
    # 고도는 양 끝(0m, 10m) 사이를 나눈다
    assert graph.nodes[node].elevation == pytest.approx(6.0)
    # P 는 Q 로 바로 가지 않고 나눈 지점을 거친다
    assert sorted(arc.target for arc in graph.adjacency[0]) == [2, 3]
    assert sorted((arc.target, arc.length) for arc in graph.adjacency[node]) == [
        (0, pytest.approx(120)),
        (1, pytest.approx(80)),
    ]
    # 원래 그래프는 그대로다
    assert len(LINE.nodes) == 3
    assert sorted(arc.target for arc in LINE.adjacency[0]) == [1, 2]


def test_path_from_point_on_road() -> None:
    [start, *_] = nearby_road_points(LINE, *at(120, 8), 100)
    [goal, *_] = nearby_road_points(LINE, *at(-3, 50), 100)
    graph, [start_node, goal_node] = with_road_points(LINE, [start, goal])
    path = find_path(graph, start_node, goal_node, GENERAL)

    assert path is not None
    assert path.nodes == [start_node, 0, 2]
    assert sum(arc.length for arc in path.arcs) == pytest.approx(170)


def test_start_and_goal_on_same_road() -> None:
    [start, *_] = nearby_road_points(LINE, *at(150, 5), 100)
    [goal, *_] = nearby_road_points(LINE, *at(30, -5), 100)
    graph, [start_node, goal_node] = with_road_points(LINE, [start, goal])
    path = find_path(graph, start_node, goal_node, GENERAL)

    assert path is not None
    assert path.nodes == [start_node, goal_node]
    assert path.arcs[0].length == pytest.approx(120)


def test_point_at_road_end_uses_node() -> None:
    [point, *_] = nearby_road_points(LINE, *at(200.2, 3), 100)
    graph, [node] = with_road_points(LINE, [point])

    assert node == 1
    assert graph.nodes is LINE.nodes


def test_split_keeps_road_shape() -> None:
    # 0 → (50, 40) → (100, 40) → 1 로 휘어진 길을 (75, 40) 에서 나눈다
    graph = make_graph(
        [(0, 0), (150, 0)],
        [(0, 1, 50 * math.hypot(4, 5) / 5 * 2 + 50)],
        {0: [(50, 40), (100, 40)]},
    )
    [point, *_] = nearby_road_points(graph, *at(75, 45), 100)
    split, [node] = with_road_points(graph, [point])
    to_start, to_end = sorted(split.adjacency[node], key=lambda arc: arc.target)

    assert to_start.target == 0
    assert [*to_start.geometry] == [pytest.approx(at(50, 40))]
    assert to_end.target == 1
    assert [*to_end.geometry] == [pytest.approx(at(100, 40))]
    assert to_start.length + to_end.length == pytest.approx(point.edge.length)
    assert to_start.length == pytest.approx(to_end.length)
