"""이동 조건별로 서로 오갈 수 있는 노드 묶음(연결 요소)과 출발·도착 지점 고르기.

찍은 위치에서 가장 가까운 길이 계단·급경사이거나 그런 길로 둘러싸여 있으면, 근처에
갈 수 있는 길이 있어도 경로가 없다. 그래서 반경 안을 지나는 길 중 이동 조건으로
지나갈 수 있고, 출발·도착이 같은 묶음에 들어가는 길 위 지점을 후보로 고른다.
"""

from dataclasses import dataclass, replace
from enum import StrEnum

from core.cost import is_passable
from core.graph import Arc, Graph
from core.profiles import Profile
from core.road_point import RoadPoint, nearby_road_points

# 사용자가 경사 한계를 바꾸면 조건 조합이 늘어나므로 캐시 크기를 제한한다.
MAX_CACHED_PROFILES = 32
# 가장 가까운 길보다 이만큼(m) 더 먼 길까지 후보로 둔다.
# 가장 가까운 길이 멀리 돌아가야 하는 길이면 경로 탐색이 다른 후보를 고른다.
CANDIDATE_SLACK_M = 50.0


class EndpointFailure(StrEnum):
    START_OFF_NETWORK = "start_off_network"
    GOAL_OFF_NETWORK = "goal_off_network"
    NOT_CONNECTED = "not_connected"


@dataclass(frozen=True)
class Endpoints:
    # 출발·도착 후보 지점. 가까운 순서. 어느 후보를 쓸지는 경로 탐색이 정한다.
    starts: list[RoadPoint]
    goals: list[RoadPoint]


def passable_either_way(arc: Arc, profile: Profile) -> bool:
    """한 방향이라도 지나갈 수 있으면 True. 계단만 방향에 따라 다르다."""
    return is_passable(arc, profile) or (
        arc.steps and is_passable(replace(arc, grade=-arc.grade), profile)
    )


def component_labels(graph: Graph, profile: Profile) -> list[int]:
    """노드마다 연결 요소 번호. 통행 가능 여부에 쓰이는 조건이 같으면 캐시를 쓴다."""
    key = (
        profile.max_grade,
        profile.stairs_up,
        profile.stairs_down,
        profile.needs_wheelchair_access,
    )
    cached = graph.component_cache.get(key)
    if cached is not None:
        return cached

    labels = [-1] * len(graph.nodes)
    for root in range(len(graph.nodes)):
        if labels[root] != -1:
            continue
        labels[root] = root
        stack = [root]
        while stack:
            node = stack.pop()
            for arc in graph.adjacency[node]:
                if labels[arc.target] == -1 and passable_either_way(arc, profile):
                    labels[arc.target] = root
                    stack.append(arc.target)

    if len(graph.component_cache) >= MAX_CACHED_PROFILES:
        graph.component_cache.clear()
    graph.component_cache[key] = labels
    return labels


def pick_endpoints(
    graph: Graph,
    start: tuple[float, float],
    goal: tuple[float, float],
    profile: Profile,
    max_distance_m: float,
) -> Endpoints | EndpointFailure:
    """반경 안을 지나는 길 중 출발·도착이 같은 연결 요소에 있는 후보 지점을 고른다.

    이동 조건으로 지나갈 수 없는 길(휠체어의 계단 등)에는 붙이지 않는다.
    """
    starts = nearby_road_points(graph, *start, max_distance_m)
    if not starts:
        return EndpointFailure.START_OFF_NETWORK
    goals = nearby_road_points(graph, *goal, max_distance_m)
    if not goals:
        return EndpointFailure.GOAL_OFF_NETWORK

    labels = component_labels(graph, profile)
    # 지나갈 수 있는 길은 양 끝이 같은 묶음이라 시작 노드의 묶음을 쓴다.
    starts = [point for point in starts if passable_either_way(point.edge, profile)]
    goals = [point for point in goals if passable_either_way(point.edge, profile)]
    shared = {labels[p.edge.source] for p in starts} & {
        labels[p.edge.source] for p in goals
    }
    if not shared:
        return EndpointFailure.NOT_CONNECTED
    return Endpoints(
        candidates(starts, shared, labels), candidates(goals, shared, labels)
    )


def candidates(
    points: list[RoadPoint], shared: set[int], labels: list[int]
) -> list[RoadPoint]:
    """shared 묶음의 지점 중 가장 가까운 지점보다 CANDIDATE_SLACK_M 안쪽인 것."""
    usable = [point for point in points if labels[point.edge.source] in shared]
    limit = usable[0].gap_m + CANDIDATE_SLACK_M
    return [point for point in usable if point.gap_m <= limit]
