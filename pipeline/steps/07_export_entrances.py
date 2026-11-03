"""OSM 출입구와 그 출입구가 붙은 건물·시설 영역을 entrances.json.gz 로 내보낸다.

실행: pipeline/ 에서 uv run python steps/07_export_entrances.py
- 입력: Overpass API (서울 entrance=* 노드, 그 노드를 지나는 닫힌 way 와 multipolygon)
- 출력: areas [{rings: [[[lon, lat], ...]], entrances: [{lon, lat, wheelchair}]}]
  백엔드는 찍은 곳을 감싸는 가장 작은 영역의 출입구 앞 길에서 경로를 시작·끝낸다.
- 비상구·직원용 출입구, 출입 금지 출입구는 뺀다. 쓸 출입구가 없는 영역도 뺀다.
그래프(00~04 단계)와 관계가 없어서 run_all.py 에 넣지 않고 따로 실행한다.
"""

import argparse
import gzip
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from common import (
    CONFIG_PATH,
    fetch_overpass,
    load_config,
    outer_rings,
    outer_ways,
    point,
    repo_path,
)


def build_query(area_name: str, timeout_s: int) -> str:
    return f"""[out:json][timeout:{timeout_s}];
area["name"="{area_name}"]["admin_level"="4"]->.target;
node["entrance"](area.target)->.entrances;
way(bn.entrances)->.ways;
rel(bw.ways)["type"="multipolygon"]->.relations;
.entrances out;
.ways out body geom;
.relations out body geom;
"""


def usable_entrance(node: dict[str, Any], config: dict[str, Any]) -> bool:
    tags = node.get("tags", {})
    return (
        tags.get("entrance") not in config["excluded_entrances"]
        and tags.get("access") not in config["excluded_access"]
    )


def is_area(tags: dict[str, str], area_keys: list[str]) -> bool:
    return any(key in tags for key in area_keys)


def build_areas(
    elements: list[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """출입구가 붙은 영역마다 고리와 쓸 수 있는 출입구 목록."""
    entrances = {
        e["id"]: e
        for e in elements
        if e["type"] == "node" and usable_entrance(e, config)
    }
    ways = {e["id"]: e for e in elements if e["type"] == "way"}

    def entrances_on(way_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = {n for w in way_ids if w in ways for n in ways[w]["nodes"]}
        return [
            {
                "lon": point(entrances[n])[0],
                "lat": point(entrances[n])[1],
                "wheelchair": entrances[n].get("tags", {}).get("wheelchair"),
            }
            for n in sorted(ids & entrances.keys())
        ]

    areas = []
    for element in elements:
        if not is_area(element.get("tags", {}), config["area_keys"]):
            continue
        if element["type"] == "way":
            found = entrances_on([element["id"]])
        elif element["type"] == "relation":
            found = entrances_on(m["ref"] for m in outer_ways(element))
        else:
            continue
        rings = outer_rings(element)
        if rings and found:
            areas.append({"rings": rings, "entrances": found})
    return areas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    settings = load_config(parser.parse_args().config)
    overpass, config = settings["overpass"], settings["entrances"]
    output = repo_path(config["output"])

    query = build_query(overpass["area_name"], config["timeout_s"])
    data = fetch_overpass(overpass, query, config["timeout_s"])
    areas = build_areas(data["elements"], config)
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wt", encoding="utf-8") as f:
        json.dump({"areas": areas}, f, ensure_ascii=False, separators=(",", ":"))
    entrances = sum(len(area["entrances"]) for area in areas)
    print(f"영역 {len(areas):,}개, 출입구 {entrances:,}개 → {output}", flush=True)


if __name__ == "__main__":
    main()
