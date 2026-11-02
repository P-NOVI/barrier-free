"""보행 도로망 구간마다 계단·경사로와 통행 가능 여부를 정한다.

실행: pipeline/ 에서 uv run python steps/03_tag_barriers.py
- steps: highway=steps
- ramp: ramp=yes 또는 ramp:wheelchair=yes
- walk_ok: foot 가 허용이면 true, 아니면 access=no · private 일 때 false
- wheelchair_ok: 계단 · wheelchair=no · walk_ok=false 이면 false
"""

import argparse
import math
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import osmnx as ox

from common import CONFIG_PATH, data_path, load_config, require_files

FOOT_ALLOWED = {"yes", "designated", "permissive"}
ACCESS_BLOCKED = {"no", "private"}


def tag_values(data: Mapping[str, Any], tag: str) -> set[str]:
    """태그 값을 집합으로. 단순화로 합쳐진 구간은 값이 리스트일 수 있다."""
    value = data.get(tag)
    values = value if isinstance(value, list) else [value]
    return {
        str(v)
        for v in values
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    }


def barrier_tags(data: Mapping[str, Any]) -> dict[str, bool]:
    steps = "steps" in tag_values(data, "highway")
    ramp = "yes" in tag_values(data, "ramp") | tag_values(data, "ramp:wheelchair")
    foot = tag_values(data, "foot")
    walk_ok = bool(foot & FOOT_ALLOWED) or not (
        tag_values(data, "access") & ACCESS_BLOCKED
    )
    wheelchair_ok = walk_ok and not steps and "no" not in tag_values(data, "wheelchair")
    return {
        "steps": steps,
        "ramp": ramp,
        "walk_ok": walk_ok,
        "wheelchair_ok": wheelchair_ok,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)
    source = data_path(config["elevation"]["output"])
    output = data_path(config["barriers"]["output"])
    require_files(source)

    started = time.time()
    graph = ox.load_graphml(source)
    counts = {"steps": 0, "ramp": 0, "walk_ok": 0, "wheelchair_ok": 0}
    for _, _, data in graph.edges(data=True):
        tags = barrier_tags(data)
        data.update(tags)
        for key, value in tags.items():
            counts[key] += value
    ox.save_graphml(graph, output)

    total = graph.number_of_edges()
    print(
        f"edges {total}: steps {counts['steps']}, ramp {counts['ramp']}, "
        f"walk_ok=false {total - counts['walk_ok']}, "
        f"wheelchair_ok=false {total - counts['wheelchair_ok']}",
        flush=True,
    )
    print(f"saved {output} ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
