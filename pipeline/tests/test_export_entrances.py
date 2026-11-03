import importlib.util
from pathlib import Path

STEPS = Path(__file__).resolve().parents[1] / "steps"
CONFIG = {
    "area_keys": ["building", "amenity"],
    "excluded_entrances": ["emergency", "service"],
    "excluded_access": ["private", "no"],
}


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


entrances = load_step("07_export_entrances.py")


def node(node_id: int, lon: float, lat: float, **tags: str) -> dict:
    return {"type": "node", "id": node_id, "lon": lon, "lat": lat, "tags": tags}


def geometry(points: list[tuple[float, float]]) -> list[dict]:
    return [{"lon": lon, "lat": lat} for lon, lat in points]


SQUARE = [(127.0, 37.5), (127.001, 37.5), (127.001, 37.501), (127.0, 37.501)]


def building(way_id: int, nodes: list[int], points: list, **tags: str) -> dict:
    return {
        "type": "way",
        "id": way_id,
        "nodes": nodes,
        "geometry": geometry(points),
        "tags": tags or {"building": "yes"},
    }


def test_building_keeps_usable_entrances() -> None:
    elements = [
        node(1, 127.0, 37.5, entrance="main", wheelchair="yes"),
        node(2, 127.001, 37.5, entrance="emergency"),
        node(3, 127.001, 37.501, entrance="yes", access="private"),
        building(10, [1, 2, 3, 4, 1], [*SQUARE, SQUARE[0]]),
    ]

    areas = entrances.build_areas(elements, CONFIG)

    assert areas == [
        {
            "rings": [[*SQUARE, SQUARE[0]]],
            "entrances": [{"lon": 127.0, "lat": 37.5, "wheelchair": "yes"}],
        }
    ]


def test_skips_open_ways_untagged_areas_and_areas_without_entrances() -> None:
    elements = [
        node(1, 127.0, 37.5, entrance="yes"),
        node(2, 127.001, 37.5, entrance="service"),
        # 닫히지 않은 담장
        building(10, [1, 5, 6], SQUARE[:3]),
        # 영역 태그가 없음
        building(11, [1, 5, 6, 7, 1], [*SQUARE, SQUARE[0]], barrier="fence"),
        # 직원용 출입구만 있음
        building(12, [2, 5, 6, 7, 2], [*SQUARE, SQUARE[0]]),
    ]

    assert entrances.build_areas(elements, CONFIG) == []


def test_multipolygon_joins_outer_pieces() -> None:
    first = [SQUARE[0], SQUARE[1], SQUARE[2]]
    # 방향이 반대인 조각도 잇는다.
    second = [SQUARE[0], SQUARE[3], SQUARE[2]]
    elements = [
        node(1, *SQUARE[1], entrance="yes"),
        {"type": "way", "id": 20, "nodes": [9, 1, 8], "geometry": geometry(first)},
        {
            "type": "relation",
            "id": 30,
            "tags": {"type": "multipolygon", "amenity": "hospital"},
            "members": [
                {
                    "type": "way",
                    "ref": 20,
                    "role": "outer",
                    "geometry": geometry(first),
                },
                {
                    "type": "way",
                    "ref": 21,
                    "role": "outer",
                    "geometry": geometry(second),
                },
            ],
        },
    ]

    [area] = entrances.build_areas(elements, CONFIG)

    [ring] = area["rings"]
    assert ring[0] == ring[-1]
    assert set(ring) == set(SQUARE)
    assert area["entrances"] == [{"lon": 127.001, "lat": 37.5, "wheelchair": None}]


def test_query_names_area_and_timeout() -> None:
    query = entrances.build_query("서울특별시", 120)

    assert "[timeout:120]" in query
    assert 'area["name"="서울특별시"]' in query
