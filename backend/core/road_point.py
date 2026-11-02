"""출발·도착 좌표를 가장 가까운 길 위 지점에 붙인다.

노드(교차점·길 끝)에만 붙이면, 바로 옆을 지나는 긴 길을 두고 다른 길의 노드로
돌아가는 경로가 나온다. 그래서 길 위 지점을 찾고, 그 길을 그 지점에서 나눠
임시 노드로 경로를 찾는다. 원래 그래프는 바꾸지 않는다.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import accumulate, pairwise

from core.graph import Arc, Graph, Node, shape
from core.snap import LngLat, distance_m, project

# 길 끝에서 이 거리(m) 안이면 길을 나누지 않고 끝 노드를 쓴다.
END_M = 0.5


@dataclass(frozen=True)
class RoadPoint:
    # 지점이 놓인 길 (정방향 u → v)
    edge: Arc
    # 길 처음(u)부터 지점까지 온 비율(0~1)
    share: float
    position: LngLat
    # 찍은 좌표에서 지점까지 거리(m)
    gap_m: float


def nearby_road_points(
    graph: Graph, lon: float, lat: float, radius_m: float
) -> list[RoadPoint]:
    """radius_m 안을 지나는 길마다 가장 가까운 지점. 가까운 순서다."""
    points = []
    for index in graph.edge_index.near(lon, lat, radius_m):
        edge = graph.edges[index]
        hit = project(lon, lat, shape(graph, edge))
        if hit.distance_m <= radius_m:
            points.append(RoadPoint(edge, hit.share, hit.point, hit.distance_m))
    return sorted(points, key=lambda point: point.gap_m)


class _Nodes(Sequence[Node]):
    """원래 노드 뒤에 임시 노드를 덧붙인 목록."""

    def __init__(self, base: Sequence[Node], extra: list[Node]) -> None:
        self._base, self._extra = base, extra

    def __len__(self) -> int:
        return len(self._base) + len(self._extra)

    def __getitem__(self, index: int) -> Node:
        if index < len(self._base):
            return self._base[index]
        return self._extra[index - len(self._base)]


class _Adjacency(Sequence[Sequence[Arc]]):
    """바뀐 노드만 새 목록을 쓰는 인접리스트."""

    def __init__(
        self, base: Sequence[Sequence[Arc]], changed: dict[int, list[Arc]], size: int
    ) -> None:
        self._base, self._changed, self._size = base, changed, size

    def __len__(self) -> int:
        return self._size

    def __getitem__(self, index: int) -> Sequence[Arc]:
        if index in self._changed:
            return self._changed[index]
        return self._base[index]


def with_road_points(
    graph: Graph, points: Sequence[RoadPoint]
) -> tuple[Graph, list[int]]:
    """points 를 노드로 더한 그래프와 지점마다 노드 번호.

    지점이 길 끝에 있으면 끝 노드를 쓰고, 길 중간이면 그 길을 지점에서 나눈다.
    나눈 조각은 원래 길의 edge_id·경사·통행 조건을 그대로 쓰고, 길이는 모양을 따라
    나눈다.
    """
    extra: list[Node] = []
    ids: list[int] = []
    cuts: dict[int, list[tuple[float, int]]] = {}
    edges: dict[int, Arc] = {}
    for point in points:
        edge = point.edge
        if point.share * edge.length <= END_M:
            ids.append(edge.source)
            continue
        if (1 - point.share) * edge.length <= END_M:
            ids.append(edge.target)
            continue
        source, target = graph.nodes[edge.source], graph.nodes[edge.target]
        elevation = (
            source.elevation + (target.elevation - source.elevation) * point.share
        )
        node = len(graph.nodes) + len(extra)
        extra.append(Node(*point.position, elevation))
        cuts.setdefault(edge.edge_id, []).append((point.share, node))
        edges[edge.edge_id] = edge
        ids.append(node)

    if not extra:
        return graph, ids
    changed: dict[int, list[Arc]] = {}
    for edge_id, edge_cuts in cuts.items():
        edge = edges[edge_id]
        # 나눈 길은 양 끝 노드에서 빼고 조각으로 다시 잇는다.
        for end in (edge.source, edge.target):
            changed[end] = [
                arc
                for arc in changed.get(end, graph.adjacency[end])
                if arc.edge_id != edge_id
            ]
        for piece in pieces(graph, edge, sorted(edge_cuts)):
            backward = replace(
                piece,
                source=piece.target,
                target=piece.source,
                grade=-piece.grade,
                geometry=piece.geometry[::-1],
            )
            for arc in (piece, backward):
                changed.setdefault(arc.source, []).append(arc)

    size = len(graph.nodes) + len(extra)
    view = Graph(
        _Nodes(graph.nodes, extra),
        _Adjacency(graph.adjacency, changed, size),
        graph.node_index,
        graph.edges,
        graph.edge_index,
    )
    return view, ids


def pieces(graph: Graph, edge: Arc, cuts: list[tuple[float, int]]) -> list[Arc]:
    """edge 를 cuts(비율, 노드 번호) 에서 나눈 정방향 조각들."""
    points = shape(graph, edge)
    reached = list(
        accumulate((distance_m(*a, *b) for a, b in pairwise(points)), initial=0.0)
    )
    total = reached[-1]
    stops = [(0.0, edge.source), *cuts, (1.0, edge.target)]
    result = []
    for (start, source), (end, target) in pairwise(stops):
        inner = tuple(
            point
            for point, done in zip(points, reached, strict=True)
            if start * total < done < end * total
        )
        result.append(
            replace(
                edge,
                source=source,
                target=target,
                length=edge.length * (end - start),
                geometry=inner,
            )
        )
    return result
