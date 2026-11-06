import importlib.util
import random
from pathlib import Path

import networkx as nx
import pytest
from pyproj import Transformer
from shapely.geometry import LineString

import common

STEPS = Path(__file__).resolve().parents[1] / "steps"
CONFIG = common.load_config()
METRIC_CRS = CONFIG["barriers"]["metric_crs"]
# 서울 부근 평면 좌표(EPSG:5186) 원점
ORIGIN = (198000.0, 551000.0)
to_lonlat = Transformer.from_crs(METRIC_CRS, "EPSG:4326", always_xy=True).transform


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch_walknet = load_step("09_fetch_walknet.py")
add_sidewalks = load_step("10_add_sidewalks.py")
export_graph = load_step("04_export_graph.py")


def lonlat(x: float, y: float) -> tuple[float, float]:
    return to_lonlat(ORIGIN[0] + x, ORIGIN[1] + y)


def link_row(link_id: int, points: list[tuple[float, float]], **flags: str) -> dict:
    coords = ", ".join(f"{lon} {lat}" for lon, lat in (lonlat(*p) for p in points))
    return {
        "NODE_TYPE": "LINK",
        "LNKG_ID": float(link_id),
        "LNKG_WKT": f"LINESTRING({coords})",
        **flags,
    }


def test_fetch_all_repeats_until_every_row_is_seen() -> None:
    rows = [{"NODE_TYPE": "NODE", "NODE_ID": float(i)} for i in range(25)]
    shuffler = random.Random(1)

    def fetch_page(start: int, end: int) -> tuple[int, list[dict]]:
        # 요청마다 순서가 바뀌는 API 처럼, 페이지마다 다시 섞은 목록에서 자른다.
        shuffled = rows[:]
        shuffler.shuffle(shuffled)
        return len(rows), shuffled[start - 1 : end]

    result = fetch_walknet.fetch_all(fetch_page, page_size=10, max_passes=20)
    assert sorted(r["NODE_ID"] for r in result) == [float(i) for i in range(25)]


def test_fetch_all_stops_when_rows_stay_missing() -> None:
    def fetch_page(start: int, end: int) -> tuple[int, list[dict]]:
        return 3, [{"NODE_TYPE": "NODE", "NODE_ID": 1.0}]

    with pytest.raises(SystemExit):
        fetch_walknet.fetch_all(fetch_page, page_size=1000, max_passes=2)


def test_walknet_links_skip_flagged_and_duplicate_links() -> None:
    rows = [
        link_row(1, [(0, 0), (10, 0)], CRSWK="0"),
        link_row(1, [(0, 0), (10, 0)], CRSWK="0"),
        link_row(2, [(0, 0), (0, 10)], CRSWK="1"),
        {"NODE_TYPE": "NODE", "NODE_ID": 3.0, "NODE_WKT": "POINT(127 37.5)"},
    ]
    assert len(add_sidewalks.walknet_links(rows, ["CRSWK"])) == 1


# 동서로 가는 큰 도로(A-C-B, 200m)와 C 에서 남쪽으로 나가는 골목(C-D).
# 남쪽 인도는 골목 입구(x 95~105)에서 끊기고 북쪽 인도는 이어진다. 중심선에서 10m.
A, C, B, D = 1, 2, 3, 4
NODES = {A: (0, 0), C: (100, 0), B: (200, 0), D: (100, -60)}
SOUTH_WEST = [(0, -10), (95, -10)]
SOUTH_EAST = [(105, -10), (200, -10)]
NORTH = [(0, 10), (200, 10)]


def road_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    for n, (x, y) in NODES.items():
        lon, lat = lonlat(x, y)
        graph.add_node(n, x=lon, y=lat, elevation=10.0)
    ways = [(A, C, "primary", 11), (C, B, "primary", 11), (C, D, "residential", 12)]
    for u, v, highway, osmid in ways:
        length = LineString([NODES[u], NODES[v]]).length
        for a, b in ((u, v), (v, u)):
            graph.add_edge(
                a,
                b,
                osmid=osmid,
                highway=highway,
                length=length,
                grade=0.0,
                steps=False,
                ramp=False,
                wheelchair_ok=True,
                walk_ok=True,
            )
    return graph


def build() -> tuple[nx.MultiDiGraph, dict]:
    graph = road_graph()
    rows = [
        link_row(i, points)
        for i, points in enumerate([SOUTH_WEST, SOUTH_EAST, NORTH], start=1)
    ]
    links = add_sidewalks.walknet_links(rows, CONFIG["sidewalks"]["excluded_flags"])
    report = add_sidewalks.SidewalkBuilder(
        graph,
        links,
        CONFIG["sidewalks"],
        METRIC_CRS,
        lambda points: [10.0] * len(points),
    ).run()
    return graph, report


def near(graph: nx.MultiDiGraph, x: float, y: float) -> int:
    lon, lat = lonlat(x, y)
    return min(
        graph.nodes,
        key=lambda n: (
            (graph.nodes[n]["x"] - lon) ** 2 + (graph.nodes[n]["y"] - lat) ** 2
        ),
    )


def test_covered_centerline_is_marked_and_alley_is_not() -> None:
    graph, report = build()
    assert report["covered_segments"] == 2
    for u, v, data in graph.edges(data=True):
        if {u, v} in ({A, C}, {C, B}):
            assert data["sidewalk_separate"]
        if data["highway"] == "residential":
            assert not data["sidewalk_separate"]


def test_alley_joins_same_side_sidewalk_without_centerline_node() -> None:
    graph, _ = build()
    # 골목 쪽 인도에서 중심선 노드 C 를 거치지 않고 골목 끝 D 로 간다.
    without_center = nx.Graph(graph)
    without_center.remove_node(C)
    assert nx.has_path(without_center, near(graph, 50, -10), D)
    assert nx.has_path(without_center, near(graph, 150, -10), D)


def test_crossing_to_far_side_walks_on_the_road() -> None:
    graph, _ = build()
    north = near(graph, 100, 10)
    crossing = [data for _, v, data in graph.out_edges(C, data=True) if v == north]
    assert crossing
    assert all(data["sidewalk_separate"] for data in crossing)


def test_new_edges_get_grade_and_export_marks_only_centerlines() -> None:
    graph, _ = build()
    new = [d for _, _, d in graph.edges(data=True) if d["osmid"] < 0]
    assert new
    assert all(d["grade"] == 0.0 for d in new)
    exported = export_graph.export_graph(graph)
    separate = [e for e in exported["edges"] if e.get("sidewalk_separate")]
    assert separate
    assert all(e["sidewalk_separate"] is True for e in separate)
    assert any("sidewalk_separate" not in e for e in exported["edges"])
