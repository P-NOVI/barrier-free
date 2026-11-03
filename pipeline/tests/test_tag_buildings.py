import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Point

STEPS = Path(__file__).resolve().parents[1] / "steps"
METRIC_CRS = "EPSG:5186"
CONFIG = {"min_inside_m": 10, "min_inside_share": 0.5}
EXCLUDED = ["roof", "bridge", "no"]
# 서울 시청 근처 중부원점 TM 좌표(m)
ORIGIN = (198_000.0, 551_000.0)


def load_step(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tag_barriers = load_step("03_tag_barriers.py")
to_lonlat = Transformer.from_crs(METRIC_CRS, "EPSG:4326", always_xy=True)


def lonlat(x: float, y: float) -> tuple[float, float]:
    """ORIGIN 에서 (x, y) m 떨어진 곳의 경도·위도."""
    return to_lonlat.transform(ORIGIN[0] + x, ORIGIN[1] + y)


def geometry(points: list[tuple[float, float]]) -> list[dict]:
    return [dict(zip(("lon", "lat"), lonlat(x, y), strict=True)) for x, y in points]


def square(x: float, y: float, size: float) -> list[tuple[float, float]]:
    corners = [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]
    return [*corners, corners[0]]


def way(points: list[tuple[float, float]], **tags: str) -> dict:
    return {
        "type": "way",
        "geometry": geometry(points),
        "tags": tags or {"building": "yes"},
    }


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"building": "yes"}, True),
        ({"building": "university", "layer": "0"}, True),
        ({"building": "roof"}, False),
        ({"building": "yes", "layer": "-1"}, False),
        ({"building": "yes", "layer": "1"}, False),
        ({"building": "yes", "building:min_level": "2"}, False),
    ],
)
def test_usable_building(tags: dict, expected: bool) -> None:
    assert tag_barriers.usable_building(tags, EXCLUDED) is expected


def test_building_shapes_reads_ways_and_relations_with_courtyard() -> None:
    outer = square(0, 0, 40)
    relation = {
        "type": "relation",
        "tags": {"building": "yes", "type": "multipolygon"},
        "members": [
            # 바깥 고리가 두 조각으로 나뉘어 있다
            {"type": "way", "role": "outer", "geometry": geometry(outer[:3])},
            {"type": "way", "role": "outer", "geometry": geometry(outer[2:])},
            {"type": "way", "role": "inner", "geometry": geometry(square(10, 10, 20))},
        ],
    }
    elements = [
        way(square(100, 0, 20)),
        way(square(200, 0, 20), building="roof"),
        # 닫히지 않은 선
        way([(300, 0), (320, 0), (320, 20)]),
        relation,
    ]

    shapes = tag_barriers.building_shapes(elements, EXCLUDED)

    assert len(shapes) == 2
    courtyard = shapes[1]
    assert courtyard.contains(Point(lonlat(5, 5)))
    assert not courtyard.contains(Point(lonlat(20, 20)))


def test_measure_returns_length_inside_buildings() -> None:
    index = tag_barriers.BuildingIndex(
        tag_barriers.building_shapes([way(square(0, 0, 20))], EXCLUDED), METRIC_CRS
    )

    across = LineString([lonlat(-20, 10), lonlat(40, 10)])
    outside = LineString([lonlat(-20, 30), lonlat(40, 30)])

    assert index.measure(across) == pytest.approx((60, 20), abs=0.1)
    assert index.measure(outside) == pytest.approx((60, 0), abs=0.1)


@pytest.mark.parametrize(
    ("tags", "length_m", "inside_m", "expected"),
    [
        ({"highway": "footway"}, 30, 30, True),
        ({"highway": "corridor"}, 30, 20, True),
        # 건물 벽을 따라 조금 겹친 보도
        ({"highway": "footway"}, 30, 8, False),
        ({"highway": "footway"}, 100, 12, False),
        ({"highway": "footway", "bridge": "yes"}, 30, 30, False),
        ({"highway": "footway", "bridge": "no"}, 30, 30, True),
        ({"highway": "service", "tunnel": "building_passage"}, 30, 30, False),
        # 보행자 지하도는 쓰고, 건물 지하 차량 진입로는 막는다
        ({"highway": ["footway", "steps"], "tunnel": "yes"}, 30, 30, False),
        ({"highway": "service", "tunnel": "yes"}, 30, 30, True),
    ],
)
def test_is_through_building(
    tags: dict, length_m: float, inside_m: float, expected: bool
) -> None:
    assert (
        tag_barriers.is_through_building(tags, length_m, inside_m, CONFIG) is expected
    )


def test_through_building_is_not_walkable() -> None:
    tags = tag_barriers.barrier_tags({"highway": "footway"}, through_building=True)

    assert tags["through_building"] is True
    assert tags["walk_ok"] is False
    assert tags["wheelchair_ok"] is False


def test_load_buildings_downloads_once_and_reuses_file(tmp_path: Path) -> None:
    path = tmp_path / "interim" / "buildings.json.gz"
    overpass = {"url": "http://overpass.test", "area_name": "서울특별시"}
    answer = {"elements": [way(square(0, 0, 20))]}

    with patch.object(tag_barriers, "fetch_overpass", return_value=answer) as fetch:
        first = tag_barriers.load_buildings(path, overpass, 60)
        second = tag_barriers.load_buildings(path, overpass, 60)

    assert fetch.call_count == 1
    assert 'area["name"="서울특별시"]' in fetch.call_args.args[1]
    assert first == second == answer["elements"]
