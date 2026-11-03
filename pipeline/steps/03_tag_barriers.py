"""보행 도로망 구간마다 계단·경사로와 통행 가능 여부를 정한다.

실행: pipeline/ 에서 uv run python steps/03_tag_barriers.py
- steps: highway=steps
- ramp: ramp=yes 또는 ramp:wheelchair=yes
- through_building: OSM 건물 윤곽 안을 지나는 구간 (실내 통로, 건물 지하 진입로,
  건물 위 데크 등). 지도에는 길이 없어 건물을 뚫고 가는 것처럼 보인다.
  다리, 건물 통과 통로(tunnel=building_passage), 보행자 지하도는 뺀다.
- walk_ok: foot 가 허용이면 true, 아니면 access=no · private 일 때 false.
  through_building 이면 false
- wheelchair_ok: 계단 · wheelchair=no · walk_ok=false 이면 false
- trail: 등산로 단계. 막지 않고 백엔드가 비용 배율을 곱한다(backend/core/cost.py).
  mountain: sac_scale 이 mountain_hiking 이상, 길이 잘 안 보이거나 노면이 아주 나쁨
  hiking: sac_scale=hiking, 비포장 path·track, tracktype grade3 이상
  태그 없는 산길은 경사 배율로 피한다.
건물 윤곽은 처음 한 번 Overpass 에서 받아 interim/ 에 저장해 둔다.
"""

import argparse
import gzip
import json
import math
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import osmnx as ox
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, unary_union

from common import CONFIG_PATH, data_path, fetch_overpass, load_config, require_files

FOOT_ALLOWED = {"yes", "designated", "permissive"}
ACCESS_BLOCKED = {"no", "private"}
# 이 길만으로 된 지하 구간(tunnel=yes)은 보행자 지하도라 건물 밑을 지나도 쓴다.
PEDESTRIAN_WAYS = {"footway", "pedestrian", "path", "steps", "corridor"}
BUILDING_PASSAGE = "building_passage"
# 닫힌 고리의 최소 점 수(처음 점이 끝에 한 번 더 온다)
MIN_RING_POINTS = 4

# 등산로 단계. backend/core/graph.py 의 Trail 값과 같아야 한다.
TRAIL_HIKING = "hiking"
TRAIL_MOUNTAIN = "mountain"
MOUNTAIN_SAC_SCALES = {
    "mountain_hiking",
    "demanding_mountain_hiking",
    "alpine_hiking",
    "demanding_alpine_hiking",
    "difficult_alpine_hiking",
}
BAD_VISIBILITY = {"bad", "horrible", "no"}
BAD_SMOOTHNESS = {"very_bad", "horrible", "very_horrible", "impassable"}
TRAIL_WAYS = {"path", "track"}
UNPAVED_SURFACES = {
    "unpaved",
    "compacted",
    "fine_gravel",
    "gravel",
    "pebblestone",
    "rock",
    "dirt",
    "earth",
    "ground",
    "grass",
    "mud",
    "sand",
    "woodchips",
}
ROUGH_TRACKS = {"grade3", "grade4", "grade5"}


def tag_values(data: Mapping[str, Any], tag: str) -> set[str]:
    """태그 값을 집합으로. 단순화로 합쳐진 구간은 값이 리스트일 수 있다."""
    value = data.get(tag)
    values = value if isinstance(value, list) else [value]
    return {
        str(v)
        for v in values
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    }


def barrier_tags(
    data: Mapping[str, Any], through_building: bool = False
) -> dict[str, bool]:
    steps = "steps" in tag_values(data, "highway")
    ramp = "yes" in tag_values(data, "ramp") | tag_values(data, "ramp:wheelchair")
    foot = tag_values(data, "foot")
    walk_ok = not through_building and (
        bool(foot & FOOT_ALLOWED) or not (tag_values(data, "access") & ACCESS_BLOCKED)
    )
    wheelchair_ok = walk_ok and not steps and "no" not in tag_values(data, "wheelchair")
    return {
        "steps": steps,
        "ramp": ramp,
        "through_building": through_building,
        "walk_ok": walk_ok,
        "wheelchair_ok": wheelchair_ok,
    }


def trail_level(data: Mapping[str, Any]) -> str | None:
    """등산로 단계. 등산로가 아니면 None."""
    if (
        tag_values(data, "sac_scale") & MOUNTAIN_SAC_SCALES
        or tag_values(data, "trail_visibility") & BAD_VISIBILITY
        or tag_values(data, "smoothness") & BAD_SMOOTHNESS
    ):
        return TRAIL_MOUNTAIN
    unpaved_trail = tag_values(data, "highway") & TRAIL_WAYS and (
        tag_values(data, "surface") & UNPAVED_SURFACES
    )
    if (
        "hiking" in tag_values(data, "sac_scale")
        or unpaved_trail
        or tag_values(data, "tracktype") & ROUGH_TRACKS
    ):
        return TRAIL_HIKING
    return None


def building_query(area_name: str, timeout_s: int) -> str:
    return f"""[out:json][timeout:{timeout_s}];
area["name"="{area_name}"]["admin_level"="4"]->.target;
(way["building"](area.target);
 relation["building"]["type"="multipolygon"](area.target););
out tags geom;
"""


def usable_building(tags: Mapping[str, str], excluded: Iterable[str]) -> bool:
    """밑이나 위를 걸어 다닐 수 있는 지붕·공중·지하 건물이 아닌지."""
    return (
        tags.get("building") not in set(excluded)
        and tags.get("layer", "0") == "0"
        and "min_level" not in tags
        and "building:min_level" not in tags
    )


def rings(lines: list[LineString]) -> list[Polygon]:
    """조각난 multipolygon 고리들을 이어 닫힌 고리만 다각형으로."""
    if not lines:
        return []
    merged = linemerge(lines)
    parts = merged.geoms if hasattr(merged, "geoms") else [merged]
    return [
        Polygon(part.coords)
        for part in parts
        if part.is_ring and len(part.coords) >= MIN_RING_POINTS
    ]


def building_shapes(
    elements: list[dict[str, Any]], excluded: Iterable[str]
) -> list[BaseGeometry]:
    """Overpass 응답의 건물 윤곽(경도·위도). 안뜰(inner)은 뚫어 둔다."""
    shapes: list[BaseGeometry] = []
    for element in elements:
        if not usable_building(element.get("tags", {}), excluded):
            continue
        if element["type"] == "way":
            points = [(g["lon"], g["lat"]) for g in element.get("geometry", [])]
            if len(points) >= MIN_RING_POINTS and points[0] == points[-1]:
                shapes.append(Polygon(points))
        elif element["type"] == "relation":
            members: dict[str, list[LineString]] = {"outer": [], "inner": []}
            for member in element.get("members", []):
                geometry = member.get("geometry") or []
                if member.get("role") in members and len(geometry) >= 2:
                    line = LineString([(g["lon"], g["lat"]) for g in geometry])
                    members[member["role"]].append(line)
            outer = unary_union(rings(members["outer"]))
            if not outer.is_empty:
                shapes.append(outer.difference(unary_union(rings(members["inner"]))))
    return [shape if shape.is_valid else shape.buffer(0) for shape in shapes]


class BuildingIndex:
    """평면 좌표(m)로 옮긴 건물 윤곽과 검색 트리."""

    def __init__(self, shapes: list[BaseGeometry], metric_crs: str) -> None:
        self._to_metric = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
        self._shapes = [self._project(shape) for shape in shapes]
        self._tree = shapely.STRtree(self._shapes)

    def _project(self, geometry: BaseGeometry) -> BaseGeometry:
        return shapely.transform(geometry, self._transform)

    def _transform(self, xy: np.ndarray) -> np.ndarray:
        return np.column_stack(self._to_metric.transform(xy[:, 0], xy[:, 1]))

    def measure(self, line: LineString) -> tuple[float, float]:
        """경도·위도 선의 (전체 길이, 건물 안 길이) m."""
        projected = self._project(line)
        hits = self._tree.query(projected, predicate="intersects")
        if len(hits) == 0:
            return projected.length, 0.0
        inside = projected.intersection(unary_union([self._shapes[i] for i in hits]))
        return projected.length, inside.length


def building_exempt(data: Mapping[str, Any]) -> bool:
    """건물 윤곽과 겹쳐도 쓰는 구간: 다리, 건물 통과 통로, 보행자 지하도."""
    if tag_values(data, "bridge") - {"no"}:
        return True
    tunnel = tag_values(data, "tunnel")
    if BUILDING_PASSAGE in tunnel:
        return True
    return "yes" in tunnel and tag_values(data, "highway") <= PEDESTRIAN_WAYS


def is_through_building(
    data: Mapping[str, Any],
    length_m: float,
    inside_m: float,
    config: Mapping[str, Any],
) -> bool:
    if building_exempt(data) or length_m <= 0:
        return False
    return (
        inside_m >= config["min_inside_m"]
        and inside_m / length_m >= config["min_inside_share"]
    )


def load_buildings(path: Path, overpass: dict[str, Any], timeout_s: int) -> list:
    """저장해 둔 건물 윤곽 응답. 없으면 Overpass 에서 받아 저장한다."""
    if not path.exists():
        print("건물 윤곽 받는 중 (Overpass)", flush=True)
        query = building_query(overpass["area_name"], timeout_s)
        data = fetch_overpass(overpass, query, timeout_s)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)["elements"]


def edge_line(graph: Any, u: Any, v: Any, data: Mapping[str, Any]) -> LineString:
    if "geometry" in data:
        return data["geometry"]
    start, end = graph.nodes[u], graph.nodes[v]
    return LineString([(start["x"], start["y"]), (end["x"], end["y"])])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)
    barriers = config["barriers"]
    source = data_path(config["elevation"]["output"])
    output = data_path(barriers["output"])
    require_files(source)

    started = time.time()
    elements = load_buildings(
        data_path(barriers["buildings"]),
        config["overpass"],
        barriers["buildings_timeout_s"],
    )
    buildings = BuildingIndex(
        building_shapes(elements, barriers["excluded_buildings"]),
        barriers["metric_crs"],
    )
    graph = ox.load_graphml(source)
    keys = ("steps", "ramp", "through_building", "walk_ok", "wheelchair_ok")
    counts = dict.fromkeys(keys, 0)
    trails: Counter[str] = Counter()
    for u, v, data in graph.edges(data=True):
        length_m, inside_m = buildings.measure(edge_line(graph, u, v, data))
        tags = barrier_tags(
            data, is_through_building(data, length_m, inside_m, barriers)
        )
        data.update(tags)
        for key, value in tags.items():
            counts[key] += value
        if trail := trail_level(data):
            data["trail"] = trail
            trails[trail] += 1
    ox.save_graphml(graph, output)

    total = graph.number_of_edges()
    print(
        f"edges {total}: steps {counts['steps']}, ramp {counts['ramp']}, "
        f"through_building {counts['through_building']}, trail {dict(trails)}, "
        f"walk_ok=false {total - counts['walk_ok']}, "
        f"wheelchair_ok=false {total - counts['wheelchair_ok']}",
        flush=True,
    )
    print(f"saved {output} ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
