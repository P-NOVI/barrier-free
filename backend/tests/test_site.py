import gzip
import json
from pathlib import Path

from app.repositories.road_repository import load_sites
from core.site import NO_SITES, WallCrossing, build_site_index


def square(west: float, south: float, size: float) -> list[list[float]]:
    east, north = west + size, south + size
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


CAMPUS = {"rings": [square(127.0, 37.5, 0.01)]}
# 캠퍼스 안 부속 학교
SCHOOL = {"rings": [square(127.004, 37.504, 0.002)]}
OUTSIDE = (127.02, 37.505)
IN_CAMPUS = (127.001, 37.509)
IN_SCHOOL = (127.005, 37.505)


def test_gap_ending_inside_other_site() -> None:
    index = build_site_index({"sites": [CAMPUS, SCHOOL]})

    assert index.wall_crossing(OUTSIDE, IN_CAMPUS) is WallCrossing.INTO
    assert index.wall_crossing(IN_CAMPUS, IN_SCHOOL) is WallCrossing.INTO


def test_gap_through_other_site() -> None:
    index = build_site_index({"sites": [CAMPUS, SCHOOL]})
    # 캠퍼스 서쪽 밖에서 동쪽 밖까지 캠퍼스를 가로지른다.
    across_campus = index.wall_crossing((126.999, 37.505), (127.011, 37.505))
    # 캠퍼스 안에서 부속 학교를 가로질러 캠퍼스 안 길로 간다.
    across_school = index.wall_crossing((127.003, 37.505), (127.007, 37.505))

    assert across_campus is WallCrossing.THROUGH
    assert across_school is WallCrossing.THROUGH


def test_gap_within_site_or_leaving_home_site_crosses_no_wall() -> None:
    index = build_site_index({"sites": [CAMPUS, SCHOOL]})

    assert index.wall_crossing(IN_CAMPUS, (127.002, 37.502)) is WallCrossing.NONE
    assert index.wall_crossing(IN_SCHOOL, IN_CAMPUS) is WallCrossing.NONE
    assert index.wall_crossing(IN_CAMPUS, OUTSIDE) is WallCrossing.NONE
    assert index.wall_crossing(OUTSIDE, (127.02, 37.52)) is WallCrossing.NONE
    assert NO_SITES.wall_crossing(OUTSIDE, IN_CAMPUS) is WallCrossing.NONE


def test_gap_from_entrance_leaves_by_home_site() -> None:
    # 캠퍼스 안 건물을 찍고 캠퍼스 동문(경계 위) 출입구에서 밖 길로 나간다.
    index = build_site_index({"sites": [CAMPUS]})
    gate, road = (127.01, 37.505), (127.012, 37.505)

    assert index.wall_crossing(gate, road, home=IN_CAMPUS) is WallCrossing.NONE


def test_load_sites(tmp_path: Path) -> None:
    path = tmp_path / "sites.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"sites": [CAMPUS, SCHOOL]}, f)

    assert len(load_sites(path)) == 2
    assert load_sites(tmp_path / "missing.json.gz") is NO_SITES
