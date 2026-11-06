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
SIDEWALK_ROWS = [
    link_row(i, points)
    for i, points in enumerate([SOUTH_WEST, SOUTH_EAST, NORTH], start=1)
]


def road_graph() -> nx.MultiDiGraph:
    return graph_of(
        NODES,
        [(A, C, "primary", 11), (C, B, "primary", 11), (C, D, "residential", 12)],
    )


def graph_of(
    nodes: dict[int, tuple[float, float]], ways: list[tuple[int, int, str, int]]
) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    for n, (x, y) in nodes.items():
        lon, lat = lonlat(x, y)
        graph.add_node(n, x=lon, y=lat, elevation=10.0)
    for u, v, highway, osmid in ways:
        length = LineString([nodes[u], nodes[v]]).length
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


def build(
    rows: list[dict] | None = None, graph: nx.MultiDiGraph | None = None
) -> tuple[nx.MultiDiGraph, dict]:
    rows = SIDEWALK_ROWS if rows is None else rows
    graph = road_graph() if graph is None else graph
    settings = CONFIG["sidewalks"]
    links = add_sidewalks.walknet_links(rows, settings["excluded_flags"])
    crosswalks = add_sidewalks.walknet_crosswalks(
        rows, settings["crosswalk_flags"], settings["excluded_flags"]
    )
    report = add_sidewalks.SidewalkBuilder(
        graph,
        links,
        settings,
        METRIC_CRS,
        lambda points: [10.0] * len(points),
        crosswalks,
    ).run()
    return graph, report


def off_road(graph: nx.MultiDiGraph) -> nx.Graph:
    """차도(sidewalk_separate)를 뺀 그래프."""
    walk = nx.Graph()
    walk.add_nodes_from(graph.nodes)
    walk.add_edges_from(
        (u, v) for u, v, d in graph.edges(data=True) if not d["sidewalk_separate"]
    )
    return walk


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


def test_walknet_crosswalks_take_flagged_links_without_other_flags() -> None:
    rows = [
        link_row(1, [(0, 0), (10, 0)], BLDG="1"),
        link_row(2, [(0, 0), (0, 10)], BLDG="1", TNL="1"),
        link_row(3, [(0, 0), (10, 10)]),
    ]
    found = add_sidewalks.walknet_crosswalks(rows, ["BLDG"], ["BLDG", "TNL"])
    assert len(found) == 1


def test_far_side_is_reached_only_on_the_road_without_crosswalk() -> None:
    graph, report = build()
    assert report["crosswalks"] == 0
    assert not nx.has_path(off_road(graph), near(graph, 95, -10), near(graph, 0, 10))


def test_crosswalk_over_covered_road_joins_both_sidewalks() -> None:
    graph, report = build(
        [*SIDEWALK_ROWS, link_row(9, [(150, -10), (150, 10)], BLDG="1")]
    )
    assert report["crosswalks"] == 1
    crossings = [
        d for _, _, d in graph.edges(data=True) if d.get("footway") == "crossing"
    ]
    assert crossings
    assert not any(d["sidewalk_separate"] for d in crossings)
    assert nx.has_path(off_road(graph), near(graph, 95, -10), near(graph, 0, 10))


def test_crosswalk_away_from_covered_roads_is_skipped() -> None:
    _, report = build([*SIDEWALK_ROWS, link_row(9, [(100, -30), (110, -40)], BLDG="1")])
    assert report["crosswalks"] == 0


def test_corner_links_join_crosswalk_ends_to_sidewalks() -> None:
    # 횡단보도 끝은 인도에서 10m 떨어져 있고, 모퉁이 링크가 인도 중간에 닿는다.
    rows = [
        *SIDEWALK_ROWS,
        link_row(9, [(150, -20), (150, 20)], BLDG="1"),
        link_row(10, [(150, 20), (160, 10)]),
        link_row(11, [(150, -20), (160, -10)]),
        # 한 끝만 닿는 링크는 넣지 않는다.
        link_row(12, [(150, -20), (145, -40)]),
    ]
    graph, report = build(rows)
    assert report["corner_links"] == 2
    assert nx.has_path(off_road(graph), near(graph, 95, -10), near(graph, 0, 10))


def test_short_big_road_between_covered_centerlines_is_marked() -> None:
    # 교차로 안 조각 P-Q(20m)는 옆 인도가 멀어 덮이지 않지만 차도다.
    w, p, q, e = 1, 2, 3, 4
    graph = graph_of(
        {w: (0, 0), p: (100, 0), q: (120, 0), e: (220, 0)},
        [(w, p, "primary", 11), (p, q, "primary", 12), (q, e, "primary", 13)],
    )
    sidewalks = [
        [(0, 10), (70, 10)],
        [(0, -10), (70, -10)],
        [(150, 10), (220, 10)],
        [(150, -10), (220, -10)],
    ]
    rows = [link_row(i, points) for i, points in enumerate(sidewalks, start=1)]
    graph, report = build(rows, graph)
    assert report["covered_segments"] == 2
    assert report["intersection_pieces"] == 1
    piece = [d for u, v, d in graph.edges(data=True) if {u, v} == {p, q}]
    assert piece
    assert all(d["sidewalk_separate"] for d in piece)


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
