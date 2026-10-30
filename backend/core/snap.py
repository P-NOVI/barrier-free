import math
from collections import defaultdict
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.graph import Graph

EARTH_RADIUS_M = 6_371_000.0
METERS_PER_DEGREE = EARTH_RADIUS_M * math.pi / 180
# 격자 한 칸 크기. 서울에서 약 220m(남북) × 175m(동서)
CELL_DEGREES = 0.002


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


class NodeIndex:
    """노드 좌표 격자 색인. 찍은 위치의 칸부터 한 바퀴씩 넓혀 가며 찾는다.

    k 번째 바퀴까지 본 뒤 찾은 거리가 k 칸 폭 이하이면, 더 바깥 칸에는
    그보다 가까운 노드가 있을 수 없으므로 멈춘다. 결과는 전체 탐색과 같다.
    """

    __slots__ = ("_points", "_cell", "_cells", "_bounds", "_max_abs_lat")

    def __init__(
        self, points: Sequence[tuple[float, float]], cell_degrees: float = CELL_DEGREES
    ) -> None:
        self._points = list(points)
        self._cell = cell_degrees
        self._cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        for index, (lon, lat) in enumerate(self._points):
            self._cells[self._key(lon, lat)].append(index)
        xs = [x for x, _ in self._cells] or [0]
        ys = [y for _, y in self._cells] or [0]
        self._bounds = (min(xs), max(xs), min(ys), max(ys))
        self._max_abs_lat = max((abs(lat) for _, lat in self._points), default=0.0)

    def _key(self, lon: float, lat: float) -> tuple[int, int]:
        return math.floor(lon / self._cell), math.floor(lat / self._cell)

    def _ring(self, cx: int, cy: int, ring: int) -> Iterator[tuple[int, int]]:
        """(cx, cy) 에서 ring 칸 떨어진 테두리 칸들. 데이터 범위 밖은 건너뛴다."""
        if ring == 0:
            yield cx, cy
            return
        min_x, max_x, min_y, max_y = self._bounds
        xs = range(max(cx - ring, min_x), min(cx + ring, max_x) + 1)
        for y in (cy - ring, cy + ring):
            if min_y <= y <= max_y:
                for x in xs:
                    yield x, y
        ys = range(max(cy - ring + 1, min_y), min(cy + ring - 1, max_y) + 1)
        for x in (cx - ring, cx + ring):
            if min_x <= x <= max_x:
                for y in ys:
                    yield x, y

    def _cell_width_m(self, lat: float) -> float:
        """한 칸을 가로지르는 최소 거리. 경도 방향은 고위도일수록 좁아진다.

        구면 근사 오차를 덮도록 조금(0.1%) 작게 잡는다.
        """
        widest_lat = max(self._max_abs_lat, abs(lat))
        return (
            self._cell * METERS_PER_DEGREE * math.cos(math.radians(widest_lat)) * 0.999
        )

    def _rings(self, lon: float, lat: float) -> Iterator[tuple[int, list[int]]]:
        """(바퀴 번호, 그 바퀴 칸들의 노드 번호) 를 안쪽부터. 데이터를 다 덮으면 끝."""
        cx, cy = self._key(lon, lat)
        min_x, max_x, min_y, max_y = self._bounds
        last_ring = max(cx - min_x, max_x - cx, cy - min_y, max_y - cy, 0)
        for ring in range(last_ring + 1):
            yield (
                ring,
                [
                    i
                    for cell in self._ring(cx, cy, ring)
                    for i in self._cells.get(cell, ())
                ],
            )

    def nearest(
        self, lon: float, lat: float, max_distance_m: float = math.inf
    ) -> tuple[int, float] | None:
        """가장 가까운 노드 번호와 거리(m). max_distance_m 안에 없으면 None."""
        cell_m = self._cell_width_m(lat)
        best_index, best_distance = -1, math.inf
        for ring, indexes in self._rings(lon, lat):
            for index in indexes:
                distance = distance_m(lon, lat, *self._points[index])
                if distance < best_distance:
                    best_index, best_distance = index, distance
            # 다음 바퀴의 노드는 모두 ring 칸 폭보다 멀다.
            if best_distance <= ring * cell_m or ring * cell_m > max_distance_m:
                break
        if best_index < 0 or best_distance > max_distance_m:
            return None
        return best_index, best_distance

    def within(
        self, lon: float, lat: float, radius_m: float
    ) -> list[tuple[int, float]]:
        """radius_m 안의 노드 번호와 거리(m)를 가까운 순으로."""
        cell_m = self._cell_width_m(lat)
        hits = []
        for ring, indexes in self._rings(lon, lat):
            for index in indexes:
                distance = distance_m(lon, lat, *self._points[index])
                if distance <= radius_m:
                    hits.append((index, distance))
            if ring * cell_m > radius_m:
                break
        return sorted(hits, key=lambda hit: hit[1])


def nearest_node(
    graph: "Graph", lon: float, lat: float, max_distance_m: float = math.inf
) -> tuple[int, float] | None:
    """가장 가까운 노드 번호와 그 거리(m). max_distance_m 안에 노드가 없으면 None."""
    return graph.node_index.nearest(lon, lat, max_distance_m)
