"""이동 조건별로 서로 오갈 수 있는 노드 묶음(연결 요소)과 출발·도착 지점 고르기.

찍은 위치에서 가장 가까운 길이 계단·급경사이거나 그런 길로 둘러싸여 있으면, 근처에
갈 수 있는 길이 있어도 경로가 없다. 그래서 반경 안을 지나는 길 중 이동 조건으로
지나갈 수 있고, 출발·도착이 같은 묶음에 들어가는 길 위 지점을 후보로 고른다.
찍은 위치가 건물·시설 안이면 그 출입구 앞 길 위 지점도 후보로 더한다.
점선 끝이 담장 너머 시설 안인 지점은 담장 밖 지점이 하나라도 있으면 뺀다.
"""

from dataclasses import dataclass, replace
from enum import StrEnum

from core.cost import is_passable
from core.entrance import NO_ENTRANCES, EntranceIndex
from core.graph import Arc, Graph
from core.profiles import Profile
from core.road_point import RoadPoint, nearby_road_points
from core.site import NO_SITES, SiteIndex, WallCrossing
from core.snap import LngLat, distance_m

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
    # 출발·도착 후보 지점. 기준점(찍은 곳, 출입구)마다 가까운 순서로 이어 붙인다.
    # 어느 후보를 쓸지는 경로 탐색이 정한다.
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
    start: LngLat,
    goal: LngLat,
    profile: Profile,
    max_distance_m: float,
    entrances: EntranceIndex = NO_ENTRANCES,
    sites: SiteIndex = NO_SITES,
) -> Endpoints | EndpointFailure:
    """반경 안을 지나는 길 중 출발·도착이 같은 연결 요소에 있는 후보 지점을 고른다.

    이동 조건으로 지나갈 수 없는 길(휠체어의 계단 등)에는 붙이지 않는다.
    """
    starts = anchored_road_points(
        graph, start, profile, max_distance_m, entrances, sites
    )
    if not any(starts):
        return EndpointFailure.START_OFF_NETWORK
    goals = anchored_road_points(graph, goal, profile, max_distance_m, entrances, sites)
    if not any(goals):
        return EndpointFailure.GOAL_OFF_NETWORK

    labels = component_labels(graph, profile)
    # 지나갈 수 있는 길은 양 끝이 같은 묶음이라 시작 노드의 묶음을 쓴다.
    starts = [
        [point for point in group if passable_either_way(point.edge, profile)]
        for group in starts
    ]
    goals = [
        [point for point in group if passable_either_way(point.edge, profile)]
        for group in goals
    ]
    shared = {labels[p.edge.source] for group in starts for p in group} & {
        labels[p.edge.source] for group in goals for p in group
    }
    if not shared:
        return EndpointFailure.NOT_CONNECTED
    return Endpoints(
        endpoint_candidates(starts, shared, labels),
        endpoint_candidates(goals, shared, labels),
    )


def anchored_road_points(
    graph: Graph,
    point: LngLat,
    profile: Profile,
    max_distance_m: float,
    entrances: EntranceIndex,
    sites: SiteIndex = NO_SITES,
) -> list[list[RoadPoint]]:
    """기준점마다 반경 안 길 위 지점들. 첫 묶음은 찍은 곳, 나머지는 출입구 기준이다.

    점선은 기준점에서 길 위 지점까지 잇는다. 시설 밖으로 나가는 것인지는 찍은
    곳으로 정한다. 시설 문 출입구는 시설 경계 위에 있어 안팎이 갈리지 않는다.
    """
    groups = [(point, nearby_road_points(graph, *point, max_distance_m))]
    for entrance in entrances.entrances_at(*point, profile.needs_wheelchair_access):
        inside_m = distance_m(*point, *entrance.position)
        groups.append(
            (
                entrance.position,
                [
                    replace(road_point, entrance=entrance.position, inside_m=inside_m)
                    for road_point in nearby_road_points(
                        graph, *entrance.position, max_distance_m
                    )
                ],
            )
        )
    return [
        [
            replace(road_point, wall=wall)
            if (wall := sites.wall_crossing(origin, road_point.position, home=point))
            else road_point
            for road_point in group
        ]
        for origin, group in groups
    ]


def endpoint_candidates(
    groups: list[list[RoadPoint]], shared: set[int], labels: list[int]
) -> list[RoadPoint]:
    """기준점마다 shared 묶음 지점 중 가장 가까운 것보다 CANDIDATE_SLACK_M 안쪽인 지점.

    점선 끝이 담장 너머 시설 안이 아닌 지점이 하나라도 있으면 그런 지점은 모두 뺀다.
    모두 담장 너머면(시설 영역이 공공 도로까지 덮어 그려진 곳 등) 남기고, 경로
    탐색이 점선 비용을 크게 센다.
    """
    usable = [[p for p in group if labels[p.edge.source] in shared] for group in groups]
    if any(p.wall < WallCrossing.INTO for group in usable for p in group):
        usable = [[p for p in group if p.wall < WallCrossing.INTO] for group in usable]
    return [p for group in usable for p in within_slack(group)]


def within_slack(points: list[RoadPoint]) -> list[RoadPoint]:
    """가장 가까운 지점보다 CANDIDATE_SLACK_M 안쪽인 지점. 가까운 순서로 받는다."""
    if not points:
        return []
    limit = points[0].gap_m + CANDIDATE_SLACK_M
    return [point for point in points if point.gap_m <= limit]
