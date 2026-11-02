from dataclasses import dataclass
from enum import StrEnum
from itertools import accumulate

from core.graph import Graph
from core.pathfinding import PathSummary, find_path, summarize
from core.profiles import Profile
from core.reachability import EndpointFailure, pick_endpoints

LngLat = tuple[float, float]


class RouteFailure(StrEnum):
    START_OFF_NETWORK = "start_off_network"
    GOAL_OFF_NETWORK = "goal_off_network"
    NO_PATH = "no_path"


ENDPOINT_FAILURES = {
    EndpointFailure.START_OFF_NETWORK: RouteFailure.START_OFF_NETWORK,
    EndpointFailure.GOAL_OFF_NETWORK: RouteFailure.GOAL_OFF_NETWORK,
    EndpointFailure.NOT_CONNECTED: RouteFailure.NO_PATH,
}


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
    # 요청 좌표에서 경로 시작·끝 지점까지 거리. 크면 화면에서 안내한다.
    start_gap_m: float
    goal_gap_m: float


def find_route(
    graph: Graph,
    start: LngLat,
    goal: LngLat,
    profile: Profile,
    max_snap_distance_m: float,
) -> Route:
    """반경 안에서 이동 조건으로 이어진 출발·도착 노드를 골라 추천 경로를 찾는다."""
    endpoints = pick_endpoints(graph, start, goal, profile, max_snap_distance_m)
    if isinstance(endpoints, EndpointFailure):
        raise RouteNotFoundError(ENDPOINT_FAILURES[endpoints])

    path = find_path(graph, endpoints.start, endpoints.goal, profile)
    if path is None:
        raise RouteNotFoundError(RouteFailure.NO_PATH)

    nodes = [graph.nodes[i] for i in path.nodes]
    return Route(
        summary=summarize(graph, path),
        coordinates=[(node.lon, node.lat) for node in nodes],
        elevations=[node.elevation for node in nodes],
        distances_m=list(accumulate((arc.length for arc in path.arcs), initial=0.0)),
        start_gap_m=endpoints.start_gap_m,
        goal_gap_m=endpoints.goal_gap_m,
    )
