from dataclasses import dataclass
from enum import StrEnum
from itertools import accumulate

from core.graph import Graph
from core.pathfinding import PathSummary, find_path, summarize
from core.profiles import Profile
from core.snap import nearest_node

LngLat = tuple[float, float]


class RouteFailure(StrEnum):
    START_OFF_NETWORK = "start_off_network"
    GOAL_OFF_NETWORK = "goal_off_network"
    NO_PATH = "no_path"


class RouteNotFoundError(Exception):
    def __init__(self, reason: RouteFailure) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True)
class Route:
    summary: PathSummary
    coordinates: list[LngLat]
    elevations: list[float]
    # 출발점부터 각 지점까지 누적 거리. 고도 단면 그래프의 x 축.
    distances_m: list[float]


def find_route(
    graph: Graph,
    start: LngLat,
    goal: LngLat,
    profile: Profile,
    max_snap_distance_m: float,
) -> Route:
    """좌표를 가장 가까운 노드로 옮긴 뒤 이동 조건에 맞는 추천 경로를 찾는다."""
    start_hit = nearest_node(graph, *start, max_snap_distance_m)
    if start_hit is None:
        raise RouteNotFoundError(RouteFailure.START_OFF_NETWORK)
    goal_hit = nearest_node(graph, *goal, max_snap_distance_m)
    if goal_hit is None:
        raise RouteNotFoundError(RouteFailure.GOAL_OFF_NETWORK)

    path = find_path(graph, start_hit[0], goal_hit[0], profile)
    if path is None:
        raise RouteNotFoundError(RouteFailure.NO_PATH)

    nodes = [graph.nodes[i] for i in path.nodes]
    return Route(
        summary=summarize(graph, path),
        coordinates=[(node.lon, node.lat) for node in nodes],
        elevations=[node.elevation for node in nodes],
        distances_m=list(accumulate((arc.length for arc in path.arcs), initial=0.0)),
    )
