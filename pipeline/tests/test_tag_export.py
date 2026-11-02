import importlib.util
from pathlib import Path
from types import ModuleType

import networkx as nx
import pytest
from shapely.geometry import LineString

STEPS = Path(__file__).resolve().parents[1] / "steps"


def load_step(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tag_barriers = load_step("03_tag_barriers.py")
export_graph = load_step("04_export_graph.py")


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"highway": "footway"}, (False, False, True, True)),
        ({"highway": "steps"}, (True, False, True, False)),
        ({"highway": ["footway", "steps"]}, (True, False, True, False)),
        ({"highway": "footway", "ramp": "yes"}, (False, True, True, True)),
        ({"highway": "footway", "ramp:wheelchair": "yes"}, (False, True, True, True)),
        ({"highway": "service", "access": "no"}, (False, False, False, False)),
        (
            {"highway": "service", "access": "no", "foot": "yes"},
            (False, False, True, True),
        ),
        ({"highway": "footway", "wheelchair": "no"}, (False, False, True, False)),
        ({"highway": "footway", "access": float("nan")}, (False, False, True, True)),
    ],
)
def test_barrier_tags(tags: dict, expected: tuple[bool, bool, bool, bool]) -> None:
    result = tag_barriers.barrier_tags(tags)
    assert (
        result["steps"],
        result["ramp"],
        result["walk_ok"],
        result["wheelchair_ok"],
    ) == expected


def edge_data(osmid: int, length: float, grade: float, **flags: bool) -> dict:
    return {
        "osmid": osmid,
        "length": length,
        "grade": grade,
        "steps": flags.get("steps", False),
        "ramp": flags.get("ramp", False),
        "wheelchair_ok": flags.get("wheelchair_ok", True),
        "walk_ok": flags.get("walk_ok", True),
    }


def test_export_keeps_one_direction_per_segment() -> None:
    graph = nx.MultiDiGraph()
    graph.add_node(10, x=126.97791234, y=37.56631234, elevation=30.04)
    graph.add_node(20, x=126.978, y=37.567, elevation=35.0)
    graph.add_edge(10, 20, **edge_data(1, 50.04, 0.1))
    graph.add_edge(20, 10, **edge_data(1, 50.04, -0.1))
    # 같은 두 노드 사이 다른 길(계단)은 따로 남는다
    graph.add_edge(10, 20, **edge_data(2, 30.0, 0.17, steps=True, wheelchair_ok=False))
    graph.add_edge(20, 10, **edge_data(2, 30.0, -0.17, steps=True, wheelchair_ok=False))

    exported = export_graph.export_graph(graph)

    assert exported["nodes"][0] == {
        "lon": 126.977912,
        "lat": 37.566312,
        "elevation": 30.0,
    }
    edges = exported["edges"]
    assert len(edges) == 2
    assert edges[0] == {
        "id": 0,
        "u": 0,
        "v": 1,
        "length": 50.0,
        "grade": 0.1,
        "steps": False,
        "ramp": False,
        "wheelchair_ok": True,
        "walk_ok": True,
    }
    assert edges[1]["steps"] is True and edges[1]["wheelchair_ok"] is False


def test_export_keeps_inner_points_from_u_to_v() -> None:
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=126.99, y=37.534, elevation=30.0)
    graph.add_node(2, x=126.991, y=37.535, elevation=32.0)
    graph.add_node(3, x=126.992, y=37.535, elevation=33.0)
    # 휘어진 길. 모양이 v 쪽부터 저장돼 있어도 u → v 순서로 바꾼다
    curve = LineString(
        [
            (126.991, 37.535),
            (126.9905, 37.53500004),
            (126.99, 37.5345),
            (126.99, 37.534),
        ]
    )
    straight = LineString([(126.99, 37.534), (126.992, 37.535)])
    graph.add_edge(1, 2, geometry=curve, **edge_data(1, 200.0, 0.01))
    graph.add_edge(1, 3, geometry=straight, **edge_data(2, 200.0, 0.01))
    graph.add_edge(2, 3, **edge_data(3, 90.0, 0.01))

    edges = export_graph.export_graph(graph)["edges"]

    assert edges[0]["geometry"] == [[126.99, 37.5345], [126.9905, 37.535]]
    # 중간 지점이 없거나 모양 정보가 없는 구간에는 geometry 가 없다
    assert "geometry" not in edges[1]
    assert "geometry" not in edges[2]


def test_export_matches_backend_graph_format() -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=126.97, y=37.56, elevation=10.0)
    graph.add_node("b", x=126.971, y=37.56, elevation=12.0)
    graph.add_edge("a", "b", **edge_data(7, 100.0, 0.02))
    graph.add_edge("b", "a", **edge_data(7, 100.0, -0.02))

    exported = export_graph.export_graph(graph)

    assert set(exported) == {"nodes", "edges"}
    assert set(exported["nodes"][0]) == {"lon", "lat", "elevation"}
    assert set(exported["edges"][0]) == {
        "id",
        "u",
        "v",
        "length",
        "grade",
        "steps",
        "ramp",
        "wheelchair_ok",
        "walk_ok",
    }
