import math

from core.graph import Graph

EARTH_RADIUS_M = 6_371_000.0


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """두 WGS84 좌표 사이 거리(m), haversine."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    h = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def nearest_node(graph: Graph, lon: float, lat: float) -> tuple[int, float]:
    """가장 가까운 노드 번호와 그 거리(m)."""
    return min(
        (
            (index, distance_m(lon, lat, node.lon, node.lat))
            for index, node in enumerate(graph.nodes)
        ),
        key=lambda item: item[1],
    )
