"""담장으로 둘러싸여 문으로만 드나드는 시설(대학·학교·병원·군부대·아파트 단지) 영역.

찍은 곳 가까이에 길이 없으면 경로는 근처 길에서 끝나고 화면이 점선으로 잇는다.
그 길이 찍은 곳을 감싸지 않는 시설 안이면 점선이 담장을 넘는다. 그런 후보는
점선 비용을 크게 올려, 시설 밖으로 돌아가는 길을 고르게 한다
(app/services/route_service.py). 데이터는 pipeline/steps/08_export_sites.py 가 만든다.
"""

from typing import Any

from core.entrance import AreaIndex, build_area
from core.snap import LngLat


class SiteIndex(AreaIndex):
    __slots__ = ()

    def walled_off(self, origin: LngLat, point: LngLat) -> bool:
        """point 를 감싸는 시설 중 origin 을 감싸지 않는 것이 있으면 True."""
        sites = self.areas_at(*point)
        if not sites:
            return False
        around_origin = {id(site) for site in self.areas_at(*origin)}
        return any(id(site) not in around_origin for site in sites)


NO_SITES = SiteIndex([])


def build_site_index(data: dict[str, Any]) -> SiteIndex:
    """sites.json 내용({"sites": [...]})으로 색인을 만든다."""
    return SiteIndex([build_area(site) for site in data["sites"]])
