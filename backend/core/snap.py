import math
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.graph import Graph

LngLat = tuple[float, float]

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


class EdgeIndex:
    """길(지점을 이은 선) 격자 색인. 선을 감싸는 상자가 걸치는 칸마다 길 번호를 둔다.

    선 모양은 따로 들고 있지 않는다. 정확한 거리는 부르는 쪽이 project 로 잰다.
    """

    __slots__ = ("_cell", "_cells")

    def __init__(
        self, shapes: Iterable[Sequence[LngLat]], cell_degrees: float = CELL_DEGREES
    ) -> None:
        self._cell = cell_degrees
        self._cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        for index, shape in enumerate(shapes):
            lons = [lon for lon, _ in shape]
            lats = [lat for _, lat in shape]
            x0, y0 = self._key(min(lons), min(lats))
            x1, y1 = self._key(max(lons), max(lats))
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    self._cells[x, y].append(index)

    def _key(self, lon: float, lat: float) -> tuple[int, int]:
        return math.floor(lon / self._cell), math.floor(lat / self._cell)

    def near(self, lon: float, lat: float, radius_m: float) -> set[int]:
        """radius_m 안을 지날 수도 있는 길 번호."""
        d_lat = radius_m / METERS_PER_DEGREE
        widest_lat = min(abs(lat) + d_lat, 89.0)
        d_lon = d_lat / math.cos(math.radians(widest_lat))
        x0, y0 = self._key(lon - d_lon, lat - d_lat)
        x1, y1 = self._key(lon + d_lon, lat + d_lat)
        return {
            index
            for x in range(x0, x1 + 1)
            for y in range(y0, y1 + 1)
            for index in self._cells.get((x, y), ())
        }


@dataclass(frozen=True)
class Projection:
    # 선 위에서 찍은 좌표에 가장 가까운 지점
    point: LngLat
    # 찍은 좌표에서 그 지점까지 거리(m)
    distance_m: float
    # 선 처음부터 그 지점까지 온 비율(0~1)
    share: float


def project(lon: float, lat: float, shape: Sequence[LngLat]) -> Projection:
    """shape 선 위에서 (lon, lat) 에 가장 가까운 지점.

    찍은 좌표 둘레를 평면으로 보고 잰다. 수백 m 안에서는 오차가 작다.
    """
    east = METERS_PER_DEGREE * math.cos(math.radians(lat))

    def local(point: LngLat) -> tuple[float, float]:
        return (point[0] - lon) * east, (point[1] - lat) * METERS_PER_DEGREE

    best = (math.inf, 0.0, shape[0])
    travelled = 0.0
    for a, b in pairwise(shape):
        (ax, ay), (bx, by) = local(a), local(b)
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        t = 0.0 if length == 0 else min(1.0, max(0.0, -(ax * dx + ay * dy) / length**2))
        distance = math.hypot(ax + t * dx, ay + t * dy)
        if distance < best[0]:
            point = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            best = (distance, travelled + t * length, point)
        travelled += length
    distance, reached, point = best
    return Projection(point, distance, reached / travelled if travelled else 0.0)


def nearest_node(
    graph: "Graph", lon: float, lat: float, max_distance_m: float = math.inf
) -> tuple[int, float] | None:
    """가장 가까운 노드 번호와 그 거리(m). max_distance_m 안에 노드가 없으면 None."""
    return graph.node_index.nearest(lon, lat, max_distance_m)
