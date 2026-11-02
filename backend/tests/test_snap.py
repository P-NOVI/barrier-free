import random

import pytest

from core.graph import Graph, build_graph
from core.snap import NodeIndex, distance_m, nearest_node


def brute_force(points: list[tuple[float, float]], lon: float, lat: float):
    return min(
        ((i, distance_m(lon, lat, *point)) for i, point in enumerate(points)),
        key=lambda item: item[1],
    )


def test_distance_one_millidegree_latitude() -> None:
    assert distance_m(126.9779, 37.5663, 126.9779, 37.5673) == pytest.approx(
        111.2, abs=0.5
    )


def test_nearest_node() -> None:
    graph = build_graph(
        {
            "nodes": [
                {"lon": 126.9779, "lat": 37.5663, "elevation": 0.0},
                {"lon": 126.9790, "lat": 37.5663, "elevation": 0.0},
                {"lon": 126.9779, "lat": 37.5680, "elevation": 0.0},
            ],
            "edges": [],
        }
    )
    hit = nearest_node(graph, 126.9788, 37.5664)
    assert hit is not None
    index, distance = hit
    assert index == 1
    assert distance == pytest.approx(distance_m(126.9788, 37.5664, 126.9790, 37.5663))


def test_nearest_node_on_sample_grid(sample_graph: Graph) -> None:
    target = sample_graph.nodes[55]
    hit = nearest_node(sample_graph, target.lon + 0.00005, target.lat - 0.00005)
    assert hit is not None
    assert hit[0] == 55
    assert hit[1] < 10


def test_index_matches_brute_force_inside_and_outside() -> None:
    rng = random.Random(7)
    # 서울 범위에 흩어진 노드와, 범위 밖까지 포함한 검색 위치
    points = [
        (rng.uniform(126.8, 127.2), rng.uniform(37.43, 37.70)) for _ in range(2000)
    ]
    index = NodeIndex(points)
    for _ in range(300):
        lon, lat = rng.uniform(126.6, 127.4), rng.uniform(37.3, 37.9)
        hit = index.nearest(lon, lat)
        expected = brute_force(points, lon, lat)
        assert hit is not None
        assert hit[1] == pytest.approx(expected[1])


def test_index_returns_none_beyond_max_distance() -> None:
    index = NodeIndex([(126.9779, 37.5663)])
    assert index.nearest(126.9779, 37.5683, max_distance_m=100) is None
    hit = index.nearest(126.9779, 37.5683, max_distance_m=300)
    assert hit is not None and hit[0] == 0


def test_empty_index() -> None:
    assert NodeIndex([]).nearest(126.9779, 37.5663) is None


def test_within_matches_brute_force_sorted() -> None:
    rng = random.Random(11)
    points = [
        (rng.uniform(126.95, 127.0), rng.uniform(37.55, 37.58)) for _ in range(500)
    ]
    index = NodeIndex(points)
    for _ in range(50):
        lon, lat = rng.uniform(126.94, 127.01), rng.uniform(37.54, 37.59)
        hits = index.within(lon, lat, 300)
        expected = sorted(
            d for d in (distance_m(lon, lat, *p) for p in points) if d <= 300
        )
        assert [d for _, d in hits] == pytest.approx(expected)
