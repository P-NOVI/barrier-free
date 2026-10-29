"""보행 도로망 노드에 DEM 고도를 넣고 구간 경사(grade)를 계산한다.

실행: pipeline/ 에서 uv run python steps/02_add_elevation.py
도로망 좌표만 DEM 좌표계로 바꿔 읽는다. DEM 을 재투영하면 고도가 한 번 더 보간된다.
"""

import argparse
import time
from collections.abc import Hashable, Mapping
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import osmnx as ox
import rasterio
import yaml
from rasterio.warp import transform

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_DIR.parent
CONFIG_PATH = PIPELINE_DIR / "config.yaml"

GRADE_DIGITS = 4
# 지면 높이와 다른 구조물. building_passage 는 지면을 지나는 건물 통로라 제외한다.
STRUCTURE_TAGS = {"bridge": {"no"}, "tunnel": {"no", "building_passage"}}

Elevations = dict[Hashable, float | None]


def load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def sample_elevations(graph: nx.MultiDiGraph, dem_path: Path) -> Elevations:
    """노드 좌표를 DEM 좌표계로 바꿔 고도를 읽는다. DEM 빈 칸·범위 밖은 None."""
    nodes = list(graph.nodes)
    lons = [graph.nodes[n]["x"] for n in nodes]
    lats = [graph.nodes[n]["y"] for n in nodes]
    with rasterio.open(dem_path) as dem:
        xs, ys = transform(graph.graph["crs"], dem.crs, lons, lats)
        values = [v[0] for v in dem.sample(zip(xs, ys, strict=True), masked=True)]
    return {
        node: None if np.ma.is_masked(value) else float(value)
        for node, value in zip(nodes, values, strict=True)
    }


def is_structure(data: Mapping[str, Any]) -> bool:
    """다리·터널 구간인지. 단순화로 합쳐진 구간은 태그 값이 리스트일 수 있다."""
    for tag, ground_values in STRUCTURE_TAGS.items():
        value = data.get(tag)
        values = value if isinstance(value, list) else [value]
        if any(v is not None and v not in ground_values for v in values):
            return True
    return False


def interpolate_structures(graph: nx.MultiDiGraph, elevations: Elevations) -> int:
    """다리·터널 안쪽 노드의 고도를 양 끝(지면과 이어진 노드) 고도로 보간한다.

    안쪽 노드는 연결된 구간이 모두 다리·터널인 노드다. 구조물 구간을 따라 잰 거리로
    역거리 가중 평균을 내며, 끝이 2개인 다리에서는 선형 보간과 같다.
    """
    structure = nx.Graph()
    for u, v, data in graph.edges(data=True):
        if is_structure(data):
            length = data["length"]
            if not structure.has_edge(u, v) or length < structure[u][v]["length"]:
                structure.add_edge(u, v, length=length)

    def inside(node: Hashable) -> bool:
        incident = [*graph.in_edges(node, data=True), *graph.out_edges(node, data=True)]
        return all(is_structure(data) for _, _, data in incident)

    updated = 0
    for component in nx.connected_components(structure):
        targets = [n for n in component if inside(n)]
        anchors = [
            n for n in component if not inside(n) and elevations.get(n) is not None
        ]
        if not targets or not anchors:
            continue
        sub = structure.subgraph(component)
        distances = {
            a: nx.single_source_dijkstra_path_length(sub, a, weight="length")
            for a in anchors
        }
        for node in targets:
            reachable = [(d[node], a) for a, d in distances.items() if node in d]
            exact = [a for dist, a in reachable if dist == 0]
            if exact:
                elevations[node] = elevations[exact[0]]
            else:
                weights = [(1 / dist, elevations[a]) for dist, a in reachable]
                total = sum(w for w, _ in weights)
                elevations[node] = sum(w * e for w, e in weights) / total
            updated += 1
    return updated


def fill_missing(
    graph: nx.MultiDiGraph, elevations: Elevations, max_passes: int
) -> int:
    """고도가 없는 노드를 고도가 있는 이웃 노드의 평균으로 채운다."""
    undirected = graph.to_undirected(as_view=True)
    filled = 0
    for _ in range(max_passes):
        updates = {}
        for node, value in elevations.items():
            if value is not None:
                continue
            known = [
                elevations[n]
                for n in undirected.neighbors(node)
                if elevations.get(n) is not None
            ]
            if known:
                updates[node] = sum(known) / len(known)
        if not updates:
            break
        elevations.update(updates)
        filled += len(updates)
    return filled


def add_grades(graph: nx.MultiDiGraph) -> None:
    """구간 경사 = (도착 고도 - 출발 고도) / 길이. 길이 0 구간은 0."""
    for u, v, data in graph.edges(data=True):
        length = data["length"]
        rise = graph.nodes[v]["elevation"] - graph.nodes[u]["elevation"]
        grade = round(rise / length, GRADE_DIGITS) if length > 0 else 0.0
        data["grade"] = grade
        data["grade_abs"] = abs(grade)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)
    network_path = REPO_ROOT / config["network"]["output"]
    dem_path = REPO_ROOT / config["dem"]["output"]
    output = REPO_ROOT / config["elevation"]["output"]

    started = time.time()
    graph = ox.load_graphml(network_path)
    elevations = sample_elevations(graph, dem_path)
    outside_dem = sum(value is None for value in elevations.values())
    interpolated = interpolate_structures(graph, elevations)
    filled = fill_missing(graph, elevations, config["elevation"]["max_fill_passes"])
    missing = [node for node, value in elevations.items() if value is None]
    if missing:
        raise SystemExit(
            f"고도를 정하지 못한 노드 {len(missing)}개 (예: {missing[:5]}). "
            "DEM 범위와 도로망 범위를 확인하세요."
        )

    nx.set_node_attributes(graph, elevations, "elevation")
    add_grades(graph)
    output.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, output)

    grades = np.array([d["grade_abs"] for _, _, d in graph.edges(data=True)])
    print(
        f"nodes {graph.number_of_nodes()}: DEM 밖·빈 칸 {outside_dem}, "
        f"다리·터널 보간 {interpolated}, 이웃 평균으로 채움 {filled}",
        flush=True,
    )
    print(
        f"edges {len(grades)}: |grade| 중앙값 {np.median(grades):.4f}, "
        f"p90 {np.percentile(grades, 90):.4f}, p99 {np.percentile(grades, 99):.4f}, "
        f"최대 {grades.max():.4f}",
        flush=True,
    )
    print(f"saved {output} ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
