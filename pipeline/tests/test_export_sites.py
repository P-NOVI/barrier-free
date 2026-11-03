import importlib.util
from pathlib import Path

STEPS = Path(__file__).resolve().parents[1] / "steps"
FILTERS = [
    {"amenity": "^(university|school)$"},
    {"landuse": "^residential$", "name": "아파트"},
]


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sites = load_step("08_export_sites.py")

SQUARE = [(127.0, 37.5), (127.001, 37.5), (127.001, 37.501), (127.0, 37.501)]


def way(way_id: int, points: list[tuple[float, float]], **tags: str) -> dict:
    return {
        "type": "way",
        "id": way_id,
        "geometry": [{"lon": lon, "lat": lat} for lon, lat in points],
        "tags": tags,
    }


def test_query_asks_ways_and_multipolygons_for_each_filter() -> None:
    query = sites.build_query("서울특별시", FILTERS, 120)

    assert "[timeout:120]" in query
    assert 'area["name"="서울특별시"]' in query
    assert 'way["amenity"~"^(university|school)$"](area.target);' in query
    assert (
        'relation["landuse"~"^residential$"]["name"~"아파트"]'
        '["type"="multipolygon"](area.target);'
    ) in query
    # relation 멤버 위치가 있어야 고리를 잇는다.
    assert "out body geom;" in query


def test_build_sites_keeps_closed_outlines_only() -> None:
    elements = [
        way(1, [*SQUARE, SQUARE[0]], amenity="school"),
        # 닫히지 않은 way
        way(2, SQUARE, amenity="school"),
    ]

    assert sites.build_sites(elements) == [{"rings": [[*SQUARE, SQUARE[0]]]}]
