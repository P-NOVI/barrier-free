"""통행 불가 제보로 막힌 길을 어떤 이동 조건으로도 지나갈 수 없게 한 그래프.

원래 그래프는 바꾸지 않는다. 막힌 길과, 그 길에 닿는 노드의 인접 목록만 바꿔 보인다.
막힌 길은 통행 판정(core/cost.is_passable)에서 빠지므로 경로 탐색, 연결 요소,
출발·도착 지점 고르기(core/reachability.py)가 모두 그 길을 쓰지 않는다.
"""

from collections.abc import Sequence
from dataclasses import replace

from core.graph import Arc, Graph

# 막힌 길 묶음별로 들고 있는 그래프 수. 연결 요소를 그래프마다 다시 구하므로
# 같은 묶음이면 만든 그래프를 다시 쓴다. 승인·만료로 묶음이 바뀌면 새로 만든다.
MAX_CACHED_CLOSURES = 4


class _Patched[T](Sequence[T]):
    """base 와 같되 changed 에 든 번호만 다른 값을 보이는 목록."""

    def __init__(self, base: Sequence[T], changed: dict[int, T]) -> None:
        self._base, self._changed = base, changed

    def __len__(self) -> int:
        return len(self._base)

    def __getitem__(self, index: int) -> T:
        if index in self._changed:
            return self._changed[index]
        return self._base[index]


def closed(arc: Arc) -> Arc:
    """어떤 이동 조건으로도 지나갈 수 없는 구간."""
    return replace(arc, walk_ok=False)


def close_edges(graph: Graph, edge_ids: frozenset[int]) -> Graph:
    """edge_ids(core.graph.Arc.edge_id) 길을 막은 그래프. 막을 길이 없으면 graph."""
    if not edge_ids:
        return graph
    cached = graph.closure_cache.get(edge_ids)
    if cached is not None:
        return cached

    edges = {
        index: closed(arc)
        for index, arc in enumerate(graph.edges)
        if arc.edge_id in edge_ids
    }
    adjacency: dict[int, Sequence[Arc]] = {}
    for edge in edges.values():
        for node in (edge.source, edge.target):
            adjacency[node] = [
                closed(arc) if arc.edge_id in edge_ids else arc
                for arc in graph.adjacency[node]
            ]
    view = Graph(
        graph.nodes,
        _Patched(graph.adjacency, adjacency),
        graph.node_index,
        _Patched(graph.edges, edges),
        graph.edge_index,
    )
    if len(graph.closure_cache) >= MAX_CACHED_CLOSURES:
        graph.closure_cache.clear()
    graph.closure_cache[edge_ids] = view
    return view
