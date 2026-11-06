import importlib.util
from pathlib import Path

import networkx as nx
import pytest

STEP = Path(__file__).resolve().parents[1] / "steps" / "02_add_elevation.py"
spec = importlib.util.spec_from_file_location("add_elevation", STEP)
assert spec is not None and spec.loader is not None
add_elevation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(add_elevation)


def walk_graph(edges: list[tuple[str, str, float, dict]]) -> nx.MultiDiGraph:
    """osmnx 보행 도로망처럼 구간마다 양방향 edge 를 만든다."""
    graph = nx.MultiDiGraph()
    for u, v, length, tags in edges:
        graph.add_edge(u, v, length=length, **tags)
        graph.add_edge(v, u, length=length, **tags)
    return graph


BRIDGE = {"bridge": "yes"}


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({}, False),
        ({"bridge": "yes"}, True),
        ({"bridge": "viaduct"}, True),
        ({"bridge": "no"}, False),
        ({"tunnel": "yes"}, True),
        ({"tunnel": "building_passage"}, False),
        ({"bridge": ["yes", "no"]}, True),
    ],
)
def test_is_structure(tags: dict, expected: bool) -> None:
    assert add_elevation.is_structure(tags) is expected


def test_bridge_inside_nodes_are_linearly_interpolated() -> None:
    # land_a - A ═ B ═ C ═ D - land_d, A·D 는 지면과 이어진 다리 끝
    graph = walk_graph(
        [
            ("land_a", "A", 50, {}),
            ("A", "B", 100, BRIDGE),
            ("B", "C", 100, BRIDGE),
            ("C", "D", 100, BRIDGE),
            ("D", "land_d", 50, {}),
        ]
    )
    elevations = {"land_a": 10.0, "A": 10.0, "B": 2.0, "C": None, "D": 40.0}
    elevations["land_d"] = 40.0

    updated = add_elevation.interpolate_structures(graph, elevations)

    assert updated == 2
    assert elevations["B"] == pytest.approx(20.0)
    assert elevations["C"] == pytest.approx(30.0)
    assert elevations["A"] == 10.0 and elevations["D"] == 40.0


def test_structure_without_known_anchor_is_left_as_is() -> None:
    graph = walk_graph(
        [("land", "A", 50, {}), ("A", "B", 100, BRIDGE), ("B", "C", 100, BRIDGE)]
    )
    elevations = {"land": 5.0, "A": None, "B": None, "C": None}

    assert add_elevation.interpolate_structures(graph, elevations) == 0
    assert elevations["B"] is None


def test_fill_missing_uses_neighbor_average() -> None:
    graph = walk_graph([("a", "x", 10, {}), ("b", "x", 10, {}), ("x", "y", 10, {})])
    elevations = {"a": 10.0, "b": 20.0, "x": None, "y": None}

    filled = add_elevation.fill_missing(graph, elevations, max_passes=5)

    assert filled == 2
    assert elevations["x"] == pytest.approx(15.0)
    assert elevations["y"] == pytest.approx(15.0)


def test_fill_missing_stops_when_nothing_is_known() -> None:
    graph = walk_graph([("a", "b", 10, {})])
    elevations = {"a": None, "b": None}

    assert add_elevation.fill_missing(graph, elevations, max_passes=5) == 0
    assert elevations == {"a": None, "b": None}


def test_add_grades_signed_by_direction() -> None:
    graph = walk_graph([("low", "high", 100, {}), ("high", "same", 0, {})])
    nx.set_node_attributes(
        graph, {"low": 10.0, "high": 15.0, "same": 15.0}, "elevation"
    )

    add_elevation.add_grades(graph)

    assert graph["low"]["high"][0]["grade"] == pytest.approx(0.05)
    assert graph["high"]["low"][0]["grade"] == pytest.approx(-0.05)
    assert graph["high"]["low"][0]["grade_abs"] == pytest.approx(0.05)
    assert graph["high"]["same"][0]["grade"] == 0.0
