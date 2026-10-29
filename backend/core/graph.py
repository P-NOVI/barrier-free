from dataclasses import dataclass, replace
from typing import Any

from core.snap import NodeIndex


# slots: 서울 전체 그래프(노드 약 17만, 구간 약 48만 방향)의 메모리를 줄인다.
@dataclass(frozen=True, slots=True)
class Node:
    lon: float
    lat: float
    elevation: float


@dataclass(frozen=True, slots=True)
class Arc:
    """도로 구간을 한 방향으로 지나가는 단위. 반대 방향은 grade 부호만 다르다."""

    edge_id: int
    source: int
    target: int
    length: float
    grade: float
    steps: bool
    wheelchair_ok: bool
    walk_ok: bool


@dataclass(frozen=True)
class Graph:
    nodes: list[Node]
    adjacency: list[list[Arc]]
    # 좌표 → 최근접 노드 검색용 (core/snap.py)
    node_index: NodeIndex


def build_graph(data: dict[str, Any]) -> Graph:
    """graph.json 내용으로 양방향 인접리스트를 만든다.

    노드 번호는 nodes 배열의 순서다.
    """
    nodes = [Node(n["lon"], n["lat"], n["elevation"]) for n in data["nodes"]]
    adjacency: list[list[Arc]] = [[] for _ in nodes]
    for edge in data["edges"]:
        forward = Arc(
            edge_id=edge["id"],
            source=edge["u"],
            target=edge["v"],
            length=edge["length"],
            grade=edge["grade"],
            steps=edge["steps"],
            wheelchair_ok=edge["wheelchair_ok"],
            walk_ok=edge["walk_ok"],
        )
        backward = replace(
            forward, source=forward.target, target=forward.source, grade=-forward.grade
        )
        adjacency[forward.source].append(forward)
        adjacency[backward.source].append(backward)
    return Graph(nodes, adjacency, NodeIndex([(n.lon, n.lat) for n in nodes]))
