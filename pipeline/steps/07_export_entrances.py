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
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from common import CONFIG_PATH, load_config, repo_path

COORD_DIGITS = 6  # 약 0.1m
# 닫힌 고리의 최소 점 수(처음 점이 끝에 한 번 더 온다)
MIN_RING_POINTS = 4

LngLat = tuple[float, float]


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


def fetch(url: str, query: str, user_agent: str, timeout_s: int) -> dict[str, Any]:
    body = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(url, data=body, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        data = json.load(response)
    if not data.get("elements"):
        raise SystemExit(
            "Overpass 응답에 출입구가 없습니다. 지역 이름과 서버를 확인하세요."
        )
    return data


def point(node: dict[str, Any]) -> LngLat:
    return (round(node["lon"], COORD_DIGITS), round(node["lat"], COORD_DIGITS))


def join_rings(segments: Iterable[list[LngLat]]) -> list[list[LngLat]]:
    """multipolygon 의 outer way 조각들을 끝점끼리 이어 닫힌 고리로 만든다.

    닫히지 않는 조각(데이터 오류, 범위 밖에서 잘린 것)은 버린다.
    """
    pending = [list(segment) for segment in segments if len(segment) >= 2]
    rings = []
    while pending:
        ring = pending.pop()
        while ring[0] != ring[-1]:
            for i, segment in enumerate(pending):
                if segment[0] == ring[-1]:
                    ring += segment[1:]
                elif segment[-1] == ring[-1]:
                    ring += segment[-2::-1]
                else:
                    continue
                pending.pop(i)
                break
            else:
                break
        if ring[0] == ring[-1] and len(ring) >= MIN_RING_POINTS:
            rings.append(ring)
    return rings


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
            ring = [point(g) for g in element["geometry"]]
            rings = [ring] if ring[0] == ring[-1] else []
            found = entrances_on([element["id"]])
        elif element["type"] == "relation":
            outers = [
                m
                for m in element["members"]
                if m["type"] == "way" and m["role"] == "outer"
            ]
            rings = join_rings(
                [point(g) for g in m["geometry"]] for m in outers if m.get("geometry")
            )
            found = entrances_on(m["ref"] for m in outers)
        else:
            continue
        rings = [ring for ring in rings if len(ring) >= MIN_RING_POINTS]
        if rings and found:
            areas.append({"rings": rings, "entrances": found})
    return areas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["entrances"]
    output = repo_path(config["output"])

    query = build_query(config["area_name"], config["timeout_s"])
    data = fetch(
        config["overpass_url"], query, config["user_agent"], config["timeout_s"]
    )
    areas = build_areas(data["elements"], config)
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wt", encoding="utf-8") as f:
        json.dump({"areas": areas}, f, ensure_ascii=False, separators=(",", ":"))
    entrances = sum(len(area["entrances"]) for area in areas)
    print(f"영역 {len(areas):,}개, 출입구 {entrances:,}개 → {output}", flush=True)


if __name__ == "__main__":
    main()
