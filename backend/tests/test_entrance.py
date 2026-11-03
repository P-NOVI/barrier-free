import gzip
import json
from pathlib import Path

from app.repositories.road_repository import load_entrances
from core.entrance import NO_ENTRANCES, build_entrance_index, contains


def square(west: float, south: float, size: float) -> list[list[float]]:
    east, north = west + size, south + size
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


CAMPUS = {
    "rings": [square(127.0, 37.5, 0.01)],
    "entrances": [{"lon": 127.0, "lat": 37.505, "wheelchair": None}],
}
BUILDING = {
    "rings": [square(127.004, 37.504, 0.001)],
    "entrances": [
        {"lon": 127.0045, "lat": 37.504, "wheelchair": "yes"},
        {"lon": 127.005, "lat": 37.5045, "wheelchair": "no"},
    ],
}


def test_contains() -> None:
    ring = [tuple(p) for p in square(127.0, 37.5, 0.01)]

    assert contains(ring, 127.005, 37.505)
    assert not contains(ring, 127.02, 37.505)
    assert not contains(ring, 127.005, 37.52)


def test_smallest_area_wins() -> None:
    index = build_entrance_index({"areas": [CAMPUS, BUILDING]})

    in_building = index.entrances_at(127.0045, 37.5045, needs_wheelchair_access=False)
    in_campus = index.entrances_at(127.001, 37.509, needs_wheelchair_access=False)

    assert [e.position for e in in_building] == [(127.0045, 37.504), (127.005, 37.5045)]
    assert [e.position for e in in_campus] == [(127.0, 37.505)]
    assert index.entrances_at(127.02, 37.5, needs_wheelchair_access=False) == []


def test_wheelchair_skips_entrances_marked_no() -> None:
    index = build_entrance_index({"areas": [BUILDING]})

    found = index.entrances_at(127.0045, 37.5045, needs_wheelchair_access=True)

    assert [e.wheelchair for e in found] == ["yes"]


def test_load_entrances(tmp_path: Path) -> None:
    path = tmp_path / "entrances.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"areas": [BUILDING]}, f)

    assert len(load_entrances(path)) == 1
    assert load_entrances(tmp_path / "missing.json.gz") is NO_ENTRANCES
