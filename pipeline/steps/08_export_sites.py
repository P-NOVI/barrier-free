"""담장으로 둘러싸여 문으로만 드나드는 시설 영역을 sites.json.gz 로 내보낸다.

실행: pipeline/ 에서 uv run python steps/08_export_sites.py
- 입력: Overpass API (서울 대학·학교·병원·군부대·아파트 단지 등의 닫힌 way 와
  multipolygon, config.yaml 의 sites.filters)
- 출력: sites [{rings: [[[lon, lat], ...]]}]
  백엔드는 찍은 곳을 감싸지 않는 시설 안 길에 출발·도착을 잘 붙이지 않는다.
  그래서 경로가 담장 너머 길에서 끝나고 점선이 담장을 넘는 일을 줄인다.
그래프(00~04 단계)와 관계가 없어서 run_all.py 에 넣지 않고 따로 실행한다.
"""

import argparse
import gzip
import json
from pathlib import Path
from typing import Any

from common import CONFIG_PATH, fetch_overpass, load_config, outer_rings, repo_path


def build_query(area_name: str, filters: list[dict[str, str]], timeout_s: int) -> str:
    """filters 의 태그 조합(값은 정규식)마다 닫힌 way 와 multipolygon 을 찾는다."""
    selectors = [
        "".join(f'["{key}"~"{value}"]' for key, value in tags.items())
        for tags in filters
    ]
    queries = "\n".join(
        f'way{s}(area.target);\nrelation{s}["type"="multipolygon"](area.target);'
        for s in selectors
    )
    return f"""[out:json][timeout:{timeout_s}];
area["name"="{area_name}"]["admin_level"="4"]->.target;
(
{queries}
);
out body geom;
"""


def build_sites(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """시설마다 바깥 고리. 닫히지 않은 way 와 고리를 못 이은 relation 은 뺀다."""
    sites = []
    for element in elements:
        rings = outer_rings(element)
        if rings:
            sites.append({"rings": rings})
    return sites


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    settings = load_config(parser.parse_args().config)
    overpass, config = settings["overpass"], settings["sites"]
    output = repo_path(config["output"])

    query = build_query(overpass["area_name"], config["filters"], config["timeout_s"])
    data = fetch_overpass(overpass, query, config["timeout_s"])
    sites = build_sites(data["elements"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wt", encoding="utf-8") as f:
        json.dump({"sites": sites}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"시설 영역 {len(sites):,}개 → {output}", flush=True)


if __name__ == "__main__":
    main()
