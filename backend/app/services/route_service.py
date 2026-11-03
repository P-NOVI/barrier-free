from dataclasses import dataclass
from enum import StrEnum
from itertools import accumulate, pairwise

from core.entrance import NO_ENTRANCES, EntranceIndex
from core.graph import Graph, Node
from core.pathfinding import Path, PathSummary, find_path_between, summarize
from core.profiles import Profile
from core.reachability import EndpointFailure, pick_endpoints
from core.road_point import RoadPoint, with_road_points
from core.site import NO_SITES, SiteIndex
from core.snap import distance_m
from core.turns import find_turns

LngLat = tuple[float, float]

# 찍은 곳에서 길까지는 길이 아닌 곳을 걷는 거리라, 경로 비용에 이 배로 더한다.
# 더 먼 길은 그만큼 경로가 짧아질 때만 고른다. 1 이상이어야 A* 결과가 가장 싸다.
GAP_COST_FACTOR = 3.0
# 건물·시설 안에서 출입구까지는 실제로 걸어 나가는 거리라 길과 같게 센다.
# 그래서 건물 가운데에서 가장 가까운 뒷길보다 출입구 앞 길을 고르기 쉽다.
INSIDE_COST_FACTOR = 1.0
# 점선이 다른 시설을 가로지르거나 그 안에서 끝나는 후보에 GAP_COST_FACTOR 대신 쓴다.
# 가로지르기만 하면 시설을 돌아서 갈 수 있어 막지 않는다. 시설 안에서 끝나는 후보는
# 반경 안 길이 모두 그럴 때만 남는다(core/reachability.py).
WALLED_GAP_COST_FACTOR = 10.0


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
class RouteTurn:
    # coordinates 에서 꺾는 갈림길이 몇 번째인지
    index: int
    # 들어온 방향에서 나가는 방향으로 꺾는 각도(도). 오른쪽이 +
    angle: float


@dataclass(frozen=True)
class Route:
    summary: PathSummary
    # 길 모양대로 따라가는 지점. 노드 사이 중간 지점도 들어 있다.
    coordinates: list[LngLat]
    elevations: list[float]
    # 출발점부터 각 지점까지 누적 거리. 고도 단면 그래프의 x 축.
    distances_m: list[float]
    # 갈림길에서 다른 길로 꺾어 들어가는 곳. 출발점에서 가까운 순서
    turns: list[RouteTurn]
    # 요청 좌표(출입구를 거치면 그 출입구)에서 경로 시작·끝 지점까지 거리.
    # 크면 화면에서 안내한다.
    start_gap_m: float
    goal_gap_m: float
    # 경로가 건물·시설 출입구에서 시작·끝나면 그 출입구 위치
    start_entrance: LngLat | None = None
    goal_entrance: LngLat | None = None


def find_route(
    graph: Graph,
    start: LngLat,
    goal: LngLat,
    profile: Profile,
    max_snap_distance_m: float,
    entrances: EntranceIndex = NO_ENTRANCES,
    sites: SiteIndex = NO_SITES,
) -> Route:
    """이동 조건으로 이어진 길 위 출발·도착 지점을 골라 추천 경로를 찾는다."""
    endpoints = pick_endpoints(
        graph, start, goal, profile, max_snap_distance_m, entrances, sites
    )
    if isinstance(endpoints, EndpointFailure):
        raise RouteNotFoundError(ENDPOINT_FAILURES[endpoints])

    # 후보 지점에서 길을 나눠 임시 노드로 더한 그래프로, 길까지 거리를 더해 가장 싼
    # 출발·도착 후보 조합을 찾는다.
    start_points = cheapest_per_spot(endpoints.starts)
    goal_points = cheapest_per_spot(endpoints.goals)
    graph, nodes = with_road_points(graph, [*start_points, *goal_points])
    starts = points_by_node(start_points, nodes[: len(start_points)])
    goals = points_by_node(goal_points, nodes[len(start_points) :])
    path = find_path_between(
        graph,
        {node: approach_cost(point) for node, point in starts.items()},
        {node: approach_cost(point) for node, point in goals.items()},
        goal,
        profile,
    )
    if path is None:
        raise RouteNotFoundError(RouteFailure.NO_PATH)

    coordinates, elevations, distances = trace(graph, path)
    # 경로 노드가 coordinates 에서 몇 번째인지. 구간마다 중간 지점과 끝 노드가 들어간다.
    node_indices = list(
        accumulate((len(arc.geometry) + 1 for arc in path.arcs), initial=0)
    )
    return Route(
        summary=summarize(graph, path),
        coordinates=coordinates,
        elevations=elevations,
        distances_m=distances,
        turns=[
            RouteTurn(node_indices[turn.step], turn.angle)
            for turn in find_turns(graph, path)
        ],
        start_gap_m=starts[path.nodes[0]].gap_m,
        goal_gap_m=goals[path.nodes[-1]].gap_m,
        start_entrance=starts[path.nodes[0]].entrance,
        goal_entrance=goals[path.nodes[-1]].entrance,
    )


def approach_cost(point: RoadPoint) -> float:
    """찍은 곳에서 길 위 지점까지 오는 비용(m 환산)."""
    gap_factor = WALLED_GAP_COST_FACTOR if point.wall else GAP_COST_FACTOR
    return point.inside_m * INSIDE_COST_FACTOR + point.gap_m * gap_factor


def cheapest_per_spot(points: list[RoadPoint]) -> list[RoadPoint]:
    """같은 길 같은 자리에 붙은 후보(여러 출입구에서 온 것)는 싼 것 하나만 둔다."""
    best: dict[tuple[int, float], RoadPoint] = {}
    for point in points:
        key = (point.edge.edge_id, point.share)
        if key not in best or approach_cost(point) < approach_cost(best[key]):
            best[key] = point
    return list(best.values())


def points_by_node(points: list[RoadPoint], nodes: list[int]) -> dict[int, RoadPoint]:
    """노드 → 그 노드에 붙은 후보. 여러 지점이 한 노드(길 끝)면 오는 비용이 싼 쪽."""
    found: dict[int, RoadPoint] = {}
    for point, node in zip(points, nodes, strict=True):
        if node not in found or approach_cost(point) < approach_cost(found[node]):
            found[node] = point
    return found


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
