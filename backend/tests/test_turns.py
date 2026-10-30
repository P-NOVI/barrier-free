import math
from itertools import pairwise

from core.graph import build_graph
from core.pathfinding import Path
from core.snap import METERS_PER_DEGREE
from core.turns import find_turns

ORIGIN = (127.0, 37.5)

Meters = tuple[float, float]


def lon_lat(x: float, y: float) -> list[float]:
    """원점에서 동쪽 x m, 북쪽 y m 인 좌표"""
    east = METERS_PER_DEGREE * math.cos(math.radians(ORIGIN[1]))
    return [ORIGIN[0] + x / east, ORIGIN[1] + y / METERS_PER_DEGREE]


def turns_along(
    points: dict[str, Meters],
    roads: list[str],
    route: str,
    shapes: dict[str, list[Meters]] | None = None,
) -> list[tuple[str, int]]:
    """이름 붙인 지점과 길(두 글자: 양 끝 지점)로 그래프를 만들고,
    route 순서로 지나갈 때 꺾는 갈림길과 각도를 돌려준다.
    """
    names = list(points)
    shapes = shapes or {}
    graph = build_graph(
        {
            "nodes": [
                dict(zip(("lon", "lat"), lon_lat(*points[name]), strict=True))
                | {"elevation": 0.0}
                for name in names
            ],
            "edges": [
                {
                    "id": i,
                    "u": names.index(road[0]),
                    "v": names.index(road[1]),
                    "length": math.dist(points[road[0]], points[road[1]]),
                    "grade": 0.0,
                    "steps": False,
                    "ramp": False,
                    "wheelchair_ok": True,
                    "walk_ok": True,
                    "geometry": [lon_lat(*point) for point in shapes.get(road, [])],
                }
                for i, road in enumerate(roads)
            ],
        }
    )
    nodes = [names.index(name) for name in route]
    arcs = [
        next(arc for arc in graph.adjacency[a] if arc.target == b)
        for a, b in pairwise(nodes)
    ]
    return [
        (route[turn.step], round(turn.angle))
        for turn in find_turns(graph, Path(nodes, arcs, 0.0))
    ]


CROSSROADS = {"A": (0, -100), "O": (0, 0), "B": (0, 100), "L": (-100, 0), "R": (100, 0)}


def test_crossroads() -> None:
    roads = ["AO", "OB", "OL", "OR"]

    assert turns_along(CROSSROADS, roads, "AOB") == []
    assert turns_along(CROSSROADS, roads, "AOR") == [("O", 90)]
    assert turns_along(CROSSROADS, roads, "AOL") == [("O", -90)]


def test_bend_without_junction_is_not_a_turn() -> None:
    assert turns_along(CROSSROADS, ["AO", "OR"], "AOR") == []


def test_t_junction_from_stem() -> None:
    assert turns_along(CROSSROADS, ["AO", "OL", "OR"], "AOR") == [("O", 90)]


def test_following_road_that_bends_at_junction() -> None:
    points = {"A": (0, -100), "O": (0, 0), "B": (40, 100), "L": (-100, 0)}

    assert turns_along(points, ["AO", "OB", "OL"], "AOB") == []


def test_fork_leaving_straight_branch() -> None:
    points = {"A": (0, -100), "O": (0, 0), "B": (-10, 100), "C": (60, 100)}
    roads = ["AO", "OB", "OC"]

    assert turns_along(points, roads, "AOB") == []
    assert turns_along(points, roads, "AOC") == [("O", 31)]


def test_nearly_straight_branch_is_not_a_turn() -> None:
    points = {"A": (0, -100), "O": (0, 0), "B": (-10, 100), "C": (4, 100)}

    assert turns_along(points, ["AO", "OB", "OC"], "AOB") == []


def test_short_jog_is_merged_away() -> None:
    # P 에서 오른쪽으로 8m 비켜 갔다가 Q 에서 다시 북쪽으로 간다.
    points = {
        "A": (0, -100),
        "P": (0, 0),
        "N": (0, 100),
        "Q": (8, 0),
        "B": (8, 100),
        "E": (100, 0),
    }

    assert turns_along(points, ["AP", "PN", "PQ", "QB", "QE"], "APQB") == []


def test_crossing_wide_road_turns_twice() -> None:
    points = {
        "A": (0, -100),
        "P": (0, 0),
        "N": (0, 100),
        "Q": (30, 0),
        "B": (30, 100),
        "E": (100, 0),
    }

    assert turns_along(points, ["AP", "PN", "PQ", "QB", "QE"], "APQB") == [
        ("P", 90),
        ("Q", -90),
    ]


def test_heading_follows_road_shape_near_junction() -> None:
    # A 에서 비스듬히 오다가 O 앞 50m 는 북쪽으로 곧게 들어온다.
    points = {"A": (-200, -60), "O": (0, 0), "B": (0, 100), "R": (100, 0)}

    assert turns_along(points, ["AO", "OB", "OR"], "AOB", {"AO": [(0, -50)]}) == []
