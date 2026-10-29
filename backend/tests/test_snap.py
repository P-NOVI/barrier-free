import pytest

from core.graph import Graph, build_graph
from core.snap import distance_m, nearest_node


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
    index, distance = nearest_node(graph, 126.9788, 37.5664)
    assert index == 1
    assert distance == pytest.approx(distance_m(126.9788, 37.5664, 126.9790, 37.5663))


def test_nearest_node_on_sample_grid(sample_graph: Graph) -> None:
    target = sample_graph.nodes[55]
    index, distance = nearest_node(
        sample_graph, target.lon + 0.00005, target.lat - 0.00005
    )
    assert index == 55
    assert distance < 10
