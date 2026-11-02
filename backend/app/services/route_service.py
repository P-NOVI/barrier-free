from dataclasses import dataclass
from enum import StrEnum
from itertools import accumulate, pairwise

from core.graph import Graph, Node
from core.pathfinding import Path, PathSummary, find_path, summarize
from core.profiles import Profile
from core.reachability import EndpointFailure, pick_endpoints
from core.snap import distance_m

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
    # 길 모양대로 따라가는 지점. 노드 사이 중간 지점도 들어 있다.
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

    coordinates, elevations, distances = trace(graph, path)
    return Route(
        summary=summarize(graph, path),
        coordinates=coordinates,
        elevations=elevations,
        distances_m=distances,
        start_gap_m=endpoints.start_gap_m,
        goal_gap_m=endpoints.goal_gap_m,
    )


def trace(graph: Graph, path: Path) -> tuple[list[LngLat], list[float], list[float]]:
    """경로를 길 모양대로 따라가는 지점과 각 지점의 고도·누적 거리.

    중간 지점의 고도·거리는 구간 양 끝 값을 그 지점까지 온 비율로 나눈다.
    """
    first = graph.nodes[path.nodes[0]]
    coordinates = [(first.lon, first.lat)]
    elevations = [first.elevation]
    distances = [0.0]
    for arc in path.arcs:
        source, target = graph.nodes[arc.source], graph.nodes[arc.target]
        travelled = distances[-1]
        for point, share in along(source, target, arc.geometry):
            coordinates.append(point)
            elevations.append(
                source.elevation + (target.elevation - source.elevation) * share
            )
            distances.append(travelled + arc.length * share)
    return coordinates, elevations, distances


def along(
    source: Node, target: Node, inner: tuple[LngLat, ...]
) -> list[tuple[LngLat, float]]:
    """source 다음 지점부터 target 까지 각 지점과, 구간에서 그 지점까지 온 비율.

    target 의 비율은 1 이다.
    """
    points = [(source.lon, source.lat), *inner, (target.lon, target.lat)]
    reached = list(accumulate(distance_m(*a, *b) for a, b in pairwise(points)))
    total = reached[-1]
    return [
        (point, done / total if total else 1.0)
        for point, done in zip(points[1:], reached, strict=True)
    ]
