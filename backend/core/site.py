"""담장으로 둘러싸여 문으로만 드나드는 시설(대학·학교·병원·군부대·아파트 단지) 영역.

찍은 곳 가까이에 길이 없으면 경로는 근처 길에서 끝나고 화면이 점선으로 잇는다.
- 점선 끝 길이 다른 시설 안이면 담장을 넘어야 닿는다. 이런 후보는 담장 밖 후보가
  있으면 쓰지 않는다(core/reachability.py).
- 점선이 다른 시설을 가로지르기만 하면 시설을 돌아서 갈 수 있다. 막지 않고 점선
  비용을 크게 센다(app/services/route_service.py).
데이터는 pipeline/steps/08_export_sites.py 가 만든다.
"""

from collections.abc import Sequence
from enum import IntEnum
from itertools import pairwise
from typing import Any

from core.entrance import Area, AreaIndex, build_area, contains
from core.snap import LngLat

Box = tuple[float, float, float, float]


class WallCrossing(IntEnum):
    NONE = 0
    # 점선이 찍은 곳·끝 길 어느 쪽도 감싸지 않는 시설을 가로지른다.
    THROUGH = 1
    # 점선 끝 길이 찍은 곳을 감싸지 않는 시설 안이다.
    INTO = 2


def orientation(a: LngLat, b: LngLat, c: LngLat) -> float:
    """a → b 에서 c 가 왼쪽이면 +, 오른쪽이면 -."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_cross(a: LngLat, b: LngLat, c: LngLat, d: LngLat) -> bool:
    """선분 ab 와 cd 가 서로 가로지르는지. 끝이 닿기만 하면 어느 쪽이든 될 수 있다."""
    return (orientation(a, b, c) > 0) != (orientation(a, b, d) > 0) and (
        orientation(c, d, a) > 0
    ) != (orientation(c, d, b) > 0)


def crosses_ring(ring: Sequence[LngLat], a: LngLat, b: LngLat, box: Box) -> bool:
    """선분 ab 가 고리 경계를 가로지르는지. box 는 ab 의 경계 상자다."""
    min_lon, min_lat, max_lon, max_lat = box
    for c, d in pairwise(ring):
        if (
            max(c[0], d[0]) < min_lon
            or min(c[0], d[0]) > max_lon
            or max(c[1], d[1]) < min_lat
            or min(c[1], d[1]) > max_lat
        ):
            continue
        if segments_cross(a, b, c, d):
            return True
    return False


def inside(site: Area, point: LngLat) -> bool:
    return any(contains(ring, *point) for ring in site.rings)


class SiteIndex(AreaIndex):
    __slots__ = ()

    def wall_crossing(
        self, origin: LngLat, point: LngLat, home: LngLat | None = None
    ) -> WallCrossing:
        """origin 에서 point 까지 잇는 점선이 넘는 담장.

        home(찍은 곳, 없으면 origin)을 감싸는 시설 밖으로 나가는 것은 넘는 것으로
        보지 않는다. 단지 안에 OSM 길이 없거나, 단지 가장자리 상가처럼 출입구가
        바깥 도로 쪽인 곳이 많다.
        """
        home = home or origin
        box = (
            min(origin[0], point[0]),
            min(origin[1], point[1]),
            max(origin[0], point[0]),
            max(origin[1], point[1]),
        )
        found = WallCrossing.NONE
        for site in self.areas_touching(*box):
            if inside(site, home):
                continue
            if inside(site, point):
                return WallCrossing.INTO
            if not found and any(
                crosses_ring(ring, origin, point, box) for ring in site.rings
            ):
                found = WallCrossing.THROUGH
        return found


NO_SITES = SiteIndex([])


def build_site_index(data: dict[str, Any]) -> SiteIndex:
    """sites.json 내용({"sites": [...]})으로 색인을 만든다."""
    return SiteIndex([build_area(site) for site in data["sites"]])
