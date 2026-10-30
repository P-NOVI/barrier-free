"""OSM 보행 도로망을 받아 graphml 로 저장한다.

실행: pipeline/ 에서 uv run python steps/01_fetch_network.py
대상 지역과 저장 경로는 pipeline/config.yaml 의 network 항목을 쓴다.
"""

import argparse
import time
from pathlib import Path

import osmnx as ox

from common import CONFIG_PATH, data_path, load_config

# 03 단계(계단·경사로·통행 가능 여부) 판정에 쓰는 태그. osmnx 기본 태그에 더한다.
EXTRA_WAY_TAGS = [
    "foot",
    "wheelchair",
    "incline",
    "ramp",
    "ramp:wheelchair",
    "step_count",
    "surface",
    "sidewalk",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["network"]
    output = data_path(config["output"])

    ox.settings.cache_folder = data_path(config["cache_folder"])
    ox.settings.useful_tags_way = [*ox.settings.useful_tags_way, *EXTRA_WAY_TAGS]
    started = time.time()
    graph = ox.graph_from_place(config["place"], network_type="walk")
    output.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, output)
    print(
        f"{config['place']}: nodes {graph.number_of_nodes()}, "
        f"edges {graph.number_of_edges()} → {output} "
        f"({time.time() - started:.0f}s)",
        flush=True,
    )


if __name__ == "__main__":
    main()
