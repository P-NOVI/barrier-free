import gzip
import json
from pathlib import Path

from app.repositories.road_repository import load_sites
from core.site import NO_SITES, build_site_index


def square(west: float, south: float, size: float) -> list[list[float]]:
    east, north = west + size, south + size
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


CAMPUS = {"rings": [square(127.0, 37.5, 0.01)]}
# 캠퍼스 안 부속 학교
SCHOOL = {"rings": [square(127.004, 37.504, 0.002)]}
OUTSIDE = (127.02, 37.505)
IN_CAMPUS = (127.001, 37.509)
IN_SCHOOL = (127.005, 37.505)


def test_road_inside_other_site_is_walled_off() -> None:
    index = build_site_index({"sites": [CAMPUS, SCHOOL]})

    assert index.walled_off(OUTSIDE, IN_CAMPUS)
    assert index.walled_off(IN_CAMPUS, IN_SCHOOL)


def test_road_in_same_site_or_outside_sites_is_open() -> None:
    index = build_site_index({"sites": [CAMPUS, SCHOOL]})

    assert not index.walled_off(IN_CAMPUS, (127.002, 37.502))
    assert not index.walled_off(IN_SCHOOL, IN_CAMPUS)
    assert not index.walled_off(IN_CAMPUS, OUTSIDE)
    assert not NO_SITES.walled_off(OUTSIDE, IN_CAMPUS)


def test_load_sites(tmp_path: Path) -> None:
    path = tmp_path / "sites.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"sites": [CAMPUS, SCHOOL]}, f)

    assert len(load_sites(path)) == 2
    assert load_sites(tmp_path / "missing.json.gz") is NO_SITES
