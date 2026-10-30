"""경로가 갈림길에서 다른 길로 꺾어 들어가는 곳을 찾는다.

갈림길이 아닌 곳은 길이 휘어도 안내하지 않는다.
갈림길에서도 원래 길을 따라가면 안내하지 않는다.
"""

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import accumulate, pairwise

from core.graph import Arc, Graph, shape
from core.pathfinding import Path
from core.snap import distance_m

LngLat = tuple[float, float]

# 갈래 방향은 갈림길에서 이 거리(m)만큼 간 지점으로 잰다.
# 갈림길 바로 옆의 작은 꺾임에 흔들리지 않게 한다.
HEADING_SAMPLE_M = 10.0
# 들어온 방향에서 이 각도(도) 안으로 이어지는 갈래 중 가장 곧은 것을 원래 길로 본다.
CONTINUE_MAX_DEG = 45.0
# 이 각도(도) 안으로 나가면 곧게 가는 것으로 보고 안내하지 않는다.
STRAIGHT_DEG = 20.0
# 이 거리(m) 안에서 이어 꺾으면(길 건너기 전 비켜 가기 등) 한 번 꺾는 것으로 보고
# 각도를 합친다.
MERGE_M = 15.0


@dataclass(frozen=True)
class JunctionTurn:
    # path.nodes 에서 갈림길이 몇 번째인지
    step: int
    # 들어온 방향에서 나가는 방향으로 꺾는 각도(도). 오른쪽이 +
    angle: float


def find_turns(graph: Graph, path: Path) -> list[JunctionTurn]:
    """경로를 따라가며 갈림길에서 원래 길을 벗어나 꺾는 곳."""
    reached = list(accumulate((arc.length for arc in path.arcs), initial=0.0))
    turns: list[JunctionTurn] = []
    last_step = 0
    for step, angle in leaving_turns(graph, path):
        if turns and reached[step] - reached[last_step] < MERGE_M:
            # 합친 곳은 꺾이기 시작하는 갈림길을 안내 지점으로 둔다.
            turns[-1] = JunctionTurn(turns[-1].step, turns[-1].angle + angle)
        else:
            turns.append(JunctionTurn(step, angle))
        last_step = step
    return [turn for turn in turns if abs(turn.angle) > STRAIGHT_DEG]


def leaving_turns(graph: Graph, path: Path) -> Iterator[tuple[int, float]]:
    """갈림길마다 원래 길을 따라가지 않으면 (path.nodes 순서, 꺾는 각도)."""
    for step, (incoming, outgoing) in enumerate(pairwise(path.arcs), start=1):
        # 들어온 구간을 뺀 갈래. 통행 조건과 상관없이 눈에 보이는 길은 모두 센다.
        branches = [
            arc
            for arc in graph.adjacency[outgoing.source]
            if arc.edge_id != incoming.edge_id
        ]
        if len(branches) < 2:
            continue
        came = shape(graph, incoming)
        arrival = heading(sample(reversed(came)), came[-1])
        angles = [(arc, turn_angle(arrival, graph, arc)) for arc in branches]
        straight, straight_angle = min(angles, key=lambda item: abs(item[1]))
        if straight == outgoing and abs(straight_angle) <= CONTINUE_MAX_DEG:
            continue
        yield step, turn_angle(arrival, graph, outgoing)


def sample(points: Iterable[LngLat]) -> LngLat:
    """첫 지점에서 선을 따라 HEADING_SAMPLE_M 만큼 간 지점. 선이 짧으면 끝 지점."""
    points = list(points)
    left = HEADING_SAMPLE_M
    for a, b in pairwise(points):
        step = distance_m(*a, *b)
        if step >= left:
            share = left / step
            return (a[0] + (b[0] - a[0]) * share, a[1] + (b[1] - a[1]) * share)
        left -= step
    return points[-1]


def turn_angle(arrival: float, graph: Graph, arc: Arc) -> float:
    """arrival 방향으로 들어와 arc 로 나갈 때 꺾는 각도(도). 오른쪽이 +"""
    points = shape(graph, arc)
    return normalize(heading(points[0], sample(points)) - arrival)


def heading(a: LngLat, b: LngLat) -> float:
    """a 에서 b 로 가는 방향. 북쪽에서 시계 방향 각도(도)."""
    east = (b[0] - a[0]) * math.cos(math.radians(a[1]))
    north = b[1] - a[1]
    return math.degrees(math.atan2(east, north))


def normalize(angle: float) -> float:
    """-180 ~ 180"""
    return (angle + 180) % 360 - 180
