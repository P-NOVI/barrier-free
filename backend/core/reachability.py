"""이동 조건별로 서로 오갈 수 있는 노드 묶음(연결 요소)과 출발·도착 노드 고르기.

찍은 위치에서 가장 가까운 노드가 계단·급경사로 둘러싸여 있으면, 근처에 갈 수
있는 길이 있어도 경로가 없다. 그래서 반경 안의 노드 중 출발·도착이 같은 묶음에
들어가는 노드를 고른다.
"""

from dataclasses import dataclass, replace
from enum import StrEnum

from core.cost import is_passable
from core.graph import Arc, Graph
from core.profiles import Profile

# 사용자가 경사 한계를 바꾸면 조건 조합이 늘어나므로 캐시 크기를 제한한다.
MAX_CACHED_PROFILES = 32


class EndpointFailure(StrEnum):
    START_OFF_NETWORK = "start_off_network"
    GOAL_OFF_NETWORK = "goal_off_network"
    NOT_CONNECTED = "not_connected"


@dataclass(frozen=True)
class Endpoints:
    start: int
    goal: int
    # 요청 좌표에서 고른 노드까지 거리(m)
    start_gap_m: float
    goal_gap_m: float


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
    """반경 안 노드 중 같은 연결 요소에 있는 출발·도착 노드를 고른다.

    가능한 묶음이 여러 개면 출발·도착까지 거리 합이 가장 작은 묶음을 쓴다.
    출발·도착이 가까울 때 둘 다 같은 노드로 모여 "이미 도착"이 되는 경우는 뺀다.
    """
    starts = graph.node_index.within(*start, max_distance_m)
    if not starts:
        return EndpointFailure.START_OFF_NETWORK
    goals = graph.node_index.within(*goal, max_distance_m)
    if not goals:
        return EndpointFailure.GOAL_OFF_NETWORK

    labels = component_labels(graph, profile)
    # 후보가 가까운 순이라 묶음마다 처음 나온 노드가 가장 가깝다.
    nearest_start: dict[int, tuple[int, float]] = {}
    for node, distance in starts:
        nearest_start.setdefault(labels[node], (node, distance))
    nearest_goal: dict[int, tuple[int, float]] = {}
    for node, distance in goals:
        nearest_goal.setdefault(labels[node], (node, distance))

    same_place = starts[0][0] == goals[0][0]
    shared = [
        c
        for c in nearest_start.keys() & nearest_goal.keys()
        if same_place or nearest_start[c][0] != nearest_goal[c][0]
    ]
    if not shared:
        return EndpointFailure.NOT_CONNECTED
    best = min(shared, key=lambda c: nearest_start[c][1] + nearest_goal[c][1])
    (start_node, start_gap), (goal_node, goal_gap) = (
        nearest_start[best],
        nearest_goal[best],
    )
    return Endpoints(start_node, goal_node, start_gap, goal_gap)
