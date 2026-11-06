from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from core.snap import EdgeIndex, LngLat, NodeIndex


# slots: 서울 전체 그래프(노드 약 17만, 구간 약 48만 방향)의 메모리를 줄인다.
@dataclass(frozen=True, slots=True)
class Node:
    lon: float
    lat: float
    elevation: float


class Trail(StrEnum):
    """등산로 단계 (pipeline/steps/03_tag_barriers.py 가 OSM 태그로 정한다)."""

    # 쉬운 등산로·비포장 산책로 (sac_scale=hiking, 비포장 path·track)
    HIKING = "hiking"
    # 험한 산길 (sac_scale=mountain_hiking 이상, 길이 잘 안 보이거나 노면이 아주 나쁨)
    MOUNTAIN = "mountain"


@dataclass(frozen=True, slots=True)
class Arc:
    """도로 구간을 한 방향으로 지나가는 단위.

    반대 방향은 grade 부호와 geometry 순서만 다르다.
    """

    edge_id: int
    source: int
    target: int
    length: float
    grade: float
    steps: bool
    wheelchair_ok: bool
    walk_ok: bool
    # source → target 사이 길 모양의 중간 지점 (경도, 위도). 곧은 구간이면 비어 있다.
    geometry: tuple[tuple[float, float], ...] = ()
    # 등산로면 그 단계. 일반 길이면 None
    trail: Trail | None = None
    # 인도가 따로 있는 큰 도로 중심선(차도). pipeline 10 단계가 정한다.
    sidewalk_separate: bool = False


@dataclass(frozen=True)
class Graph:
    # 출발·도착을 더한 그래프(core/road_point.py)는 원래 목록 위에 덧붙인 목록을 쓴다.
    nodes: Sequence[Node]
    adjacency: Sequence[Sequence[Arc]]
    # 좌표 → 최근접 노드 검색용 (core/snap.py)
    node_index: NodeIndex
    # 길마다 정방향(u → v) Arc 하나. edge_index 의 길 번호가 이 목록의 순서다.
    edges: Sequence[Arc]
    # 좌표 → 가까운 길 검색용 (core/snap.py)
    edge_index: EdgeIndex
    # 이동 조건별 연결 요소 번호 캐시 (core/reachability.py)
    component_cache: dict[tuple, list[int]] = field(
        default_factory=dict, compare=False, repr=False
    )
    # 막힌 길 묶음 → 그 길을 막은 그래프 캐시 (core/closure.py)
    closure_cache: dict[frozenset[int], "Graph"] = field(
        default_factory=dict, compare=False, repr=False
    )


def build_graph(data: dict[str, Any]) -> Graph:
    """graph.json 내용으로 양방향 인접리스트를 만든다.

    노드 번호는 nodes 배열의 순서다.
    """
    nodes = [Node(n["lon"], n["lat"], n["elevation"]) for n in data["nodes"]]
    adjacency: list[list[Arc]] = [[] for _ in nodes]
    edges: list[Arc] = []
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
            geometry=tuple((lon, lat) for lon, lat in edge.get("geometry", ())),
            trail=Trail(edge["trail"]) if "trail" in edge else None,
            sidewalk_separate=edge.get("sidewalk_separate", False),
        )
        backward = replace(
            forward,
            source=forward.target,
            target=forward.source,
            grade=-forward.grade,
            geometry=forward.geometry[::-1],
        )
        adjacency[forward.source].append(forward)
        adjacency[backward.source].append(backward)
        edges.append(forward)
    return Graph(
        nodes,
        adjacency,
        NodeIndex([(n.lon, n.lat) for n in nodes]),
        edges,
        EdgeIndex(arc_shape(nodes, arc) for arc in edges),
    )


def shape(graph: Graph, arc: Arc) -> list[LngLat]:
    """arc 의 길 모양. source 부터 target 까지 (경도, 위도)."""
    return arc_shape(graph.nodes, arc)


def arc_shape(nodes: Sequence[Node], arc: Arc) -> list[LngLat]:
    source, target = nodes[arc.source], nodes[arc.target]
    return [(source.lon, source.lat), *arc.geometry, (target.lon, target.lat)]
