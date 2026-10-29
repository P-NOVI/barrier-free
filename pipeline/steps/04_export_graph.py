"""도로망을 백엔드 경로 탐색용 graph.json.gz 로 내보낸다.

실행: pipeline/ 에서 uv run python steps/04_export_graph.py
형식은 backend/core/graph.py 의 build_graph 입력과 같다.
- nodes: [{lon, lat, elevation}], 노드 번호는 배열 순서
- edges: [{id, u, v, length, grade, steps, ramp, wheelchair_ok, walk_ok}]
  같은 길의 양방향 구간은 하나만 남기고, grade 는 u → v 방향 값이다.
"""

import argparse
import gzip
import json
import time
from collections.abc import Hashable
from pathlib import Path
from typing import Any

import networkx as nx
import osmnx as ox

from common import CONFIG_PATH, data_path, load_config, repo_path, require_files

COORD_DIGITS = 6  # 약 0.1m
ELEVATION_DIGITS = 1
LENGTH_DIGITS = 1
BOOL_TAGS = ("steps", "ramp", "wheelchair_ok", "walk_ok")


def parse_bool(value: str) -> bool:
    return value == "True"


def segment_key(u: Hashable, v: Hashable, data: dict[str, Any]) -> tuple:
    """양방향 구간을 같은 키로 묶는다.

    같은 두 노드 사이의 다른 길(계단·경사로 등)은 OSM way 로 구분한다.
    """
    osmid = data.get("osmid")
    ways = tuple(sorted(osmid)) if isinstance(osmid, list) else (osmid,)
    ends = tuple(sorted((str(u), str(v))))
    return (*ends, ways, round(data["length"], LENGTH_DIGITS))


def export_graph(graph: nx.MultiDiGraph) -> dict[str, list[dict[str, Any]]]:
    index = {node: i for i, node in enumerate(graph.nodes)}
    nodes = [
        {
            "lon": round(data["x"], COORD_DIGITS),
            "lat": round(data["y"], COORD_DIGITS),
            "elevation": round(data["elevation"], ELEVATION_DIGITS),
        }
        for _, data in graph.nodes(data=True)
    ]
    seen: set[tuple] = set()
    edges = []
    for u, v, data in graph.edges(data=True):
        key = segment_key(u, v, data)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            {
                "id": len(edges),
                "u": index[u],
                "v": index[v],
                "length": round(data["length"], LENGTH_DIGITS),
                "grade": data["grade"],
                **{tag: bool(data[tag]) for tag in BOOL_TAGS},
            }
        )
    return {"nodes": nodes, "edges": edges}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)
    source = data_path(config["barriers"]["output"])
    output = repo_path(config["export"]["output"])
    require_files(source)

    started = time.time()
    graph = ox.load_graphml(source, edge_dtypes={tag: parse_bool for tag in BOOL_TAGS})
    exported = export_graph(graph)
    text = json.dumps(exported, ensure_ascii=False, separators=(",", ":"))
    output.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0: 같은 내용이면 같은 파일이 나오도록 압축 헤더의 시각을 고정한다.
    with gzip.GzipFile(output, "wb", mtime=0) as f:
        f.write(text.encode("utf-8"))
    print(
        f"nodes {len(exported['nodes'])}, edges {len(exported['edges'])} → "
        f"{output} ({output.stat().st_size / 1e6:.1f} MB, "
        f"{time.time() - started:.0f}s)",
        flush=True,
    )


if __name__ == "__main__":
    main()
