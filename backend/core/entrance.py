"""건물·시설 영역과 그 출입구. 찍은 곳이 영역 안이면 출입구도 경로 기준점으로 쓴다.

카카오 장소 좌표는 큰 시설에서 건물 가운데에 찍혀, 가장 가까운 길이 출입구가 아닌
뒷길일 수 있다. 그래서 찍은 곳을 감싸는 가장 작은 영역의 출입구 앞 길도 출발·도착
후보로 더하고, 어느 쪽이 나은지는 경로 탐색이 정한다(core/reachability.py).
데이터는 pipeline/steps/07_export_entrances.py 가 만든다.
"""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from core.snap import CELL_DEGREES, LngLat

# OSM wheelchair 태그. 이 값인 출입구는 휠체어 조건에서 쓰지 않는다.
WHEELCHAIR_NO = "no"


@dataclass(frozen=True, slots=True)
class Entrance:
    position: LngLat
    # OSM wheelchair 태그 값(yes, no, limited). 없으면 None
    wheelchair: str | None


@dataclass(frozen=True)
class Area:
    # 바깥 고리들. 고리마다 처음 점이 끝에 한 번 더 온다.
    rings: tuple[tuple[LngLat, ...], ...]
    entrances: tuple[Entrance, ...]
    # (최소 경도, 최소 위도, 최대 경도, 최대 위도)
    bounds: tuple[float, float, float, float]
    # 고리 넓이 합(도²). 겹친 영역 중 작은 것을 고르는 비교에만 쓴다.
    size: float


def contains(ring: Sequence[LngLat], lon: float, lat: float) -> bool:
    """점이 고리 안인지(반직선 교차 수). 경계 위 점은 어느 쪽이든 될 수 있다."""
    inside = False
    for (x1, y1), (x2, y2) in pairwise(ring):
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x:
                inside = not inside
    return inside


def ring_size(ring: Sequence[LngLat]) -> float:
    """신발끈 공식 넓이(도²)."""
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in pairwise(ring))) / 2


class EntranceIndex:
    """영역 격자 색인. 영역의 경계 상자가 걸친 칸마다 영역을 넣어 둔다."""

    __slots__ = ("_areas", "_cell", "_cells")

    def __init__(
        self, areas: Sequence[Area], cell_degrees: float = CELL_DEGREES
    ) -> None:
        self._areas = list(areas)
        self._cell = cell_degrees
        self._cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        for index, area in enumerate(self._areas):
            min_lon, min_lat, max_lon, max_lat = area.bounds
            for x in range(self._key(min_lon), self._key(max_lon) + 1):
                for y in range(self._key(min_lat), self._key(max_lat) + 1):
                    self._cells[(x, y)].append(index)

    def __len__(self) -> int:
        return len(self._areas)

    def _key(self, degrees: float) -> int:
        return math.floor(degrees / self._cell)

    def area_at(self, lon: float, lat: float) -> Area | None:
        """점을 감싸는 영역 중 가장 작은 것. 캠퍼스 안 건물이면 건물을 고른다."""
        found = None
        for index in self._cells.get((self._key(lon), self._key(lat)), []):
            area = self._areas[index]
            min_lon, min_lat, max_lon, max_lat = area.bounds
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
            if found is not None and area.size >= found.size:
                continue
            if any(contains(ring, lon, lat) for ring in area.rings):
                found = area
        return found

    def entrances_at(
        self, lon: float, lat: float, needs_wheelchair_access: bool
    ) -> list[Entrance]:
        """점을 감싸는 영역의 쓸 수 있는 출입구. 영역 밖이면 빈 목록."""
        area = self.area_at(lon, lat)
        if area is None:
            return []
        return [
            entrance
            for entrance in area.entrances
            if not (needs_wheelchair_access and entrance.wheelchair == WHEELCHAIR_NO)
        ]


NO_ENTRANCES = EntranceIndex([])


def build_area(data: dict[str, Any]) -> Area:
    rings = tuple(tuple((lon, lat) for lon, lat in ring) for ring in data["rings"])
    points = [point for ring in rings for point in ring]
    return Area(
        rings=rings,
        entrances=tuple(
            Entrance((e["lon"], e["lat"]), e.get("wheelchair"))
            for e in data["entrances"]
        ),
        bounds=(
            min(lon for lon, _ in points),
            min(lat for _, lat in points),
            max(lon for lon, _ in points),
            max(lat for _, lat in points),
        ),
        size=sum(ring_size(ring) for ring in rings),
    )


def build_entrance_index(data: dict[str, Any]) -> EntranceIndex:
    """entrances.json 내용({"areas": [...]})으로 색인을 만든다."""
    return EntranceIndex([build_area(area) for area in data["areas"]])
