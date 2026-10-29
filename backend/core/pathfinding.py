import heapq
import math
from collections.abc import Mapping
from dataclasses import dataclass

from core.cost import arc_cost
from core.graph import Arc, Graph
from core.profiles import Profile


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
) -> Path | None:
    """Dijkstra 로 통행 비용 합이 가장 작은 경로를 찾는다.

    congestion 은 edge_id → 혼잡도(0~1). 갈 수 있는 길이 없으면 None.
    """
    congestion = congestion or {}
    best: dict[int, float] = {start: 0.0}
    previous: dict[int, Arc] = {}
    queue = [(0.0, start)]
    while queue:
        cost, node = heapq.heappop(queue)
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
                heapq.heappush(queue, (candidate, arc.target))

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
