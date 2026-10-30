import heapq
import math
from collections.abc import Mapping
from dataclasses import dataclass

from core.cost import arc_cost
from core.graph import Arc, Graph
from core.profiles import Profile
from core.snap import distance_m

# A* 추정치 = 목적지까지 직선거리 × 이 값. 구간 비용은 길이 × (1 이상 배율)이라
# 직선거리가 남은 비용보다 클 수 없다. 좌표·길이 반올림 오차만큼 조금 줄여 둔다.
HEURISTIC_SCALE = 0.99


@dataclass(frozen=True)
class Path:
    nodes: list[int]
    arcs: list[Arc]
    cost: float


@dataclass(frozen=True)
class PathSummary:
    distance_m: float
    # 계단을 뺀 구간 중 가장 가파른 |경사|. 계단은 steps_count 로 따로 센다.
    max_grade: float
    ascent_m: float
    steps_count: int


def find_path(
    graph: Graph,
    start: int,
    goal: int,
    profile: Profile,
    congestion: Mapping[int, float] | None = None,
    *,
    use_heuristic: bool = True,
) -> Path | None:
    """통행 비용 합이 가장 작은 경로를 A* 로 찾는다.

    목적지 쪽 노드부터 살펴 Dijkstra 보다 적게 탐색하고, 결과 비용은 같다.
    use_heuristic=False 이면 Dijkstra 와 같다.
    congestion 은 edge_id → 혼잡도(0~1). 갈 수 있는 길이 없으면 None.
    """
    congestion = congestion or {}
    target = graph.nodes[goal]

    def remaining(node: int) -> float:
        if not use_heuristic:
            return 0.0
        here = graph.nodes[node]
        return HEURISTIC_SCALE * distance_m(here.lon, here.lat, target.lon, target.lat)

    best: dict[int, float] = {start: 0.0}
    previous: dict[int, Arc] = {}
    queue = [(remaining(start), 0.0, start)]
    while queue:
        _, cost, node = heapq.heappop(queue)
        if node == goal:
            break
        if cost > best[node]:
            continue
        for arc in graph.adjacency[node]:
            step = arc_cost(arc, profile, congestion.get(arc.edge_id, 0.0))
            if math.isinf(step):
                continue
            candidate = cost + step
            if candidate < best.get(arc.target, math.inf):
                best[arc.target] = candidate
                previous[arc.target] = arc
                heapq.heappush(
                    queue, (candidate + remaining(arc.target), candidate, arc.target)
                )

    if goal not in best:
        return None
    arcs: list[Arc] = []
    node = goal
    while node != start:
        arc = previous[node]
        arcs.append(arc)
        node = arc.source
    arcs.reverse()
    return Path(
        nodes=[start, *(arc.target for arc in arcs)], arcs=arcs, cost=best[goal]
    )


def summarize(graph: Graph, path: Path) -> PathSummary:
    """경로의 거리·최대 경사·누적 상승(오르막 고도 합)·계단 구간 수."""
    rises = (
        graph.nodes[arc.target].elevation - graph.nodes[arc.source].elevation
        for arc in path.arcs
    )
    return PathSummary(
        distance_m=sum(arc.length for arc in path.arcs),
        max_grade=max(
            (abs(arc.grade) for arc in path.arcs if not arc.steps), default=0.0
        ),
        ascent_m=sum(rise for rise in rises if rise > 0),
        steps_count=sum(arc.steps for arc in path.arcs),
    )
