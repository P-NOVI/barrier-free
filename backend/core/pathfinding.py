import heapq
import math
from collections.abc import Mapping
from dataclasses import dataclass

from core.cost import arc_cost
from core.graph import Arc, Graph
from core.profiles import Profile
from core.snap import LngLat, distance_m

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
    target = graph.nodes[goal]
    return find_path_between(
        graph,
        {start: 0.0},
        {goal: 0.0},
        (target.lon, target.lat),
        profile,
        congestion,
        use_heuristic=use_heuristic,
    )


def find_path_between(
    graph: Graph,
    starts: Mapping[int, float],
    goals: Mapping[int, float],
    target: LngLat,
    profile: Profile,
    congestion: Mapping[int, float] | None = None,
    *,
    use_heuristic: bool = True,
) -> Path | None:
    """starts 의 한 노드에서 goals 의 한 노드까지, 덧붙는 비용까지 더해 가장 싼 경로.

    starts·goals 는 노드 → 그 노드에서 시작하거나 끝낼 때 더하는 비용이다.
    A* 추정치는 target 까지 직선거리라서, goals 의 덧붙는 비용이 그 노드에서
    target 까지 직선거리보다 작지 않아야 가장 싼 경로가 나온다.
    """
    congestion = congestion or {}

    def remaining(node: int) -> float:
        if not use_heuristic:
            return 0.0
        here = graph.nodes[node]
        return HEURISTIC_SCALE * distance_m(here.lon, here.lat, *target)

    best: dict[int, float] = dict(starts)
    previous: dict[int, Arc] = {}
    queue = [(cost + remaining(node), cost, node) for node, cost in starts.items()]
    heapq.heapify(queue)
    # 끝낼 노드와 덧붙는 비용까지 더한 비용. 이것보다 싼 후보가 큐에 없으면 멈춘다.
    finish: tuple[float, int] | None = None
    while queue:
        estimate, cost, node = heapq.heappop(queue)
        if finish and finish[0] <= estimate:
            break
        if cost > best[node]:
            continue
        if node in goals and (finish is None or cost + goals[node] < finish[0]):
            finish = (cost + goals[node], node)
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

    if finish is None:
        return None
    total, node = finish
    arcs: list[Arc] = []
    while node in previous:
        arc = previous[node]
        arcs.append(arc)
        node = arc.source
    arcs.reverse()
    return Path(nodes=[node, *(arc.target for arc in arcs)], arcs=arcs, cost=total)


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
