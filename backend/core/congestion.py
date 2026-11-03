"""S-DoT 센서 유동인구를 길별 혼잡도(0~1)로 바꾼다.

센서는 서울에 백여 개뿐이라 센서 반경 안 길에만 혼잡도가 붙고, 나머지 길은 0 이다.
경로 탐색은 이 값에 이동 조건별 가중치를 곱해 비용에 더한다(core/cost.py).
"""

from collections.abc import Iterable

from core.graph import Graph
from core.road_point import nearby_road_points
from core.snap import LngLat


def congestion_level(visitor_count: float, full_count: float) -> float:
    """10분 유동인구를 0~1 로 바꾼다. full_count 명 이상이면 1."""
    return min(visitor_count / full_count, 1.0)


def edge_congestion(
    graph: Graph,
    counts: Iterable[tuple[LngLat, float]],
    full_count: float,
    radius_m: float,
) -> dict[int, float]:
    """센서(위치, 10분 유동인구)마다 radius_m 안을 지나는 길의 혼잡도. edge_id → 0~1.

    한 길에 센서가 여럿 걸리면 큰 값을 쓴다.
    """
    levels: dict[int, float] = {}
    for (lon, lat), count in counts:
        level = congestion_level(count, full_count)
        if level <= 0:
            continue
        for point in nearby_road_points(graph, lon, lat, radius_m):
            edge_id = point.edge.edge_id
            levels[edge_id] = max(level, levels.get(edge_id, 0.0))
    return levels
