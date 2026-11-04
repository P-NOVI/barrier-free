"""큰 도로 중심선 옆에 서울시 도보 네트워크 인도를 넣는다.

실행: pipeline/ 에서 uv run python steps/10_add_sidewalks.py
OSM 은 큰 도로를 중심선 하나로만 그린 곳이 많아 경로선이 차도 위에 그려진다.
- 큰 도로 중심선 구간마다 sample_m 간격 지점에서 sidewalk_max_m 안에 나란한 인도 링크가
  있는지 본다. min_coverage 이상 덮이면 그 중심선에 sidewalk_separate 를 표시하고
  (경로 비용에서 불리하게), 덮은 인도 링크를 넣는다. 중심선은 지우지 않는다. 인도가
  한쪽만 있거나 끊긴 곳에서 길이 막힌다.
- 중심선 끝 노드 중 다른 길이 이어진 노드(교차로)는 양쪽 인도에 잇는다. 골목이 나가는
  쪽은 골목을 인도 위치에서 나누고 그 점을 골목 양옆 인도에 잇는다. 교차로 노드에서
  이으면 인도 → 중심선 노드 → 골목으로 뾰족하게 꺾인다.
- 중심선 노드에서 인도로 가는 선은 차도를 걷는 셈이라 sidewalk_separate 를 표시한다.
- 다른 링크 중간에 닿는 링크 끝은 그 점에서 나눠 잇는다.
- 다른 인도와 이어지지 않은 인도 끝은 가장 가까운 OSM 길(중심선 제외) 위 점에 잇는다.
  길이 없으면 가장 가까운 OSM 노드에 잇는다.
"""

import argparse
import gzip
import importlib.util
import json
import math
import time
from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Sequence
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import osmnx as ox
import rasterio
import shapely
from pyproj import Transformer
from rasterio.warp import transform as warp_transform
from shapely import STRtree, wkt
from shapely.geometry import LineString, Point
from shapely.ops import substring

from common import CONFIG_PATH, data_path, load_config, require_files

GRADE_DIGITS = 4
# 구간을 나눌 때 이보다 가까운 자르는 점은 하나로 합친다.
MIN_PIECE_M = 1.0
# 인도 링크 조각이 이보다 짧으면 넣지 않는다.
MIN_LINK_PIECE_M = 0.2

Vector = tuple[float, float]
# (경도, 위도) 목록 → 고도 목록. DEM 빈 칸은 None
ElevationOf = Callable[[Sequence[tuple[float, float]]], list[float | None]]


def _load_export_step():
    spec = importlib.util.spec_from_file_location(
        "export_graph", Path(__file__).resolve().parent / "04_export_graph.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export_step = _load_export_step()
segment_key = export_step.segment_key


def walknet_links(rows: Iterable[dict[str, Any]], excluded_flags: list[str]) -> list:
    """도보 네트워크 행의 인도 링크 모양(경위도). 같은 LNKG_ID 는 하나만."""
    links = {}
    for row in rows:
        if row["NODE_TYPE"] != "LINK":
            continue
        if any(row.get(flag) == "1" for flag in excluded_flags):
            continue
        links[row["LNKG_ID"]] = wkt.loads(row["LNKG_WKT"])
    return list(links.values())


def direction(line: LineString, at: float) -> Vector:
    a = line.interpolate(max(0.0, at - 1))
    b = line.interpolate(min(line.length, at + 1))
    dx, dy = b.x - a.x, b.y - a.y
    norm = math.hypot(dx, dy) or 1.0
    return dx / norm, dy / norm


def within_deg(a: Vector, b: Vector, max_deg: float) -> bool:
    """두 방향(부호 무시)이 max_deg 안으로 나란한지."""
    cos = abs(a[0] * b[0] + a[1] * b[1])
    return math.degrees(math.acos(min(1.0, cos))) <= max_deg


def side_of(origin: Point, axis: Vector, c: Point) -> int:
    """axis 방향으로 origin 을 지나는 선의 왼쪽이면 1, 오른쪽이면 -1."""
    cross = axis[0] * (c.y - origin.y) - axis[1] * (c.x - origin.x)
    return 1 if cross > 0 else -1


def highways(data: dict[str, Any]) -> set[str]:
    value = data.get("highway")
    return set(value) if isinstance(value, list) else {value}


class SidewalkBuilder:
    """그래프(경위도)에 인도 링크(경위도)를 넣는다. 거리 계산은 metric_crs 에서 한다."""

    def __init__(
        self,
        graph: nx.MultiDiGraph,
        links: Sequence[LineString],
        settings: dict[str, Any],
        metric_crs: str,
        elevation_of: ElevationOf,
    ) -> None:
        self.graph = graph
        self.s = settings
        self.elevation_of = elevation_of
        crs = graph.graph.get("crs", "EPSG:4326")
        self.to_m = Transformer.from_crs(crs, metric_crs, always_xy=True).transform
        self.to_lonlat = Transformer.from_crs(metric_crs, crs, always_xy=True).transform
        self.links = [self.metric(line) for line in links]
        self.link_tree = STRtree(self.links)
        self.next_id = min((n for n in graph.nodes if isinstance(n, int)), default=0)
        self.next_osmid = -1
        # 인도 링크 노드: 격자 키 → 노드 번호, 노드 번호 → 평면 좌표
        self.grid: dict[tuple[int, int], int] = {}
        self.sidewalk_nodes: dict[int, tuple[float, float]] = {}
        self.split_nodes: set[int] = set()
        self.report: dict[str, Any] = {}

    # 좌표·노드·구간 도우미

    def metric(self, geom):
        return shapely.transform(geom, self.to_m, interleaved=False)

    def lonlat(self, geom):
        return shapely.transform(geom, self.to_lonlat, interleaved=False)

    def node_point(self, n: Hashable) -> Point:
        return Point(self.to_m(self.graph.nodes[n]["x"], self.graph.nodes[n]["y"]))

    def new_node_id(self) -> int:
        self.next_id = min(self.next_id, 0) - 1
        return self.next_id

    def edge_line(self, u: Hashable, v: Hashable, data: dict[str, Any]) -> LineString:
        """u 에서 시작하는 구간 모양(평면 좌표)."""
        line = data.get("geometry")
        if line is None:
            a, b = self.graph.nodes[u], self.graph.nodes[v]
            line = LineString([(a["x"], a["y"]), (b["x"], b["y"])])
        line = self.metric(line)
        start = self.node_point(u)
        if Point(line.coords[-1]).distance(start) < Point(line.coords[0]).distance(
            start
        ):
            line = LineString(list(line.coords)[::-1])
        return line

    def sidewalk_node(self, x: float, y: float) -> int:
        grid = self.s["node_grid_m"]
        key = (round(x / grid), round(y / grid))
        if key not in self.grid:
            n = self.new_node_id()
            lon, lat = self.to_lonlat(x, y)
            self.graph.add_node(n, x=lon, y=lat)
            self.grid[key] = n
            self.sidewalk_nodes[n] = (x, y)
        return self.grid[key]

    def add_edge(
        self,
        a: int,
        b: int,
        line_m: LineString,
        highway: str,
        sidewalk_separate: bool = False,
    ) -> None:
        """새 길을 양방향으로 넣는다. 경사는 고도를 정한 뒤 finish 에서 계산한다."""
        geometry = self.lonlat(line_m)
        osmid = self.next_osmid
        self.next_osmid -= 1
        for u, v, g in (
            (a, b, geometry),
            (b, a, LineString(list(geometry.coords)[::-1])),
        ):
            self.graph.add_edge(
                u,
                v,
                osmid=osmid,
                highway=highway,
                length=line_m.length,
                geometry=g,
                steps=False,
                ramp=False,
                wheelchair_ok=True,
                walk_ok=True,
                sidewalk_separate=sidewalk_separate,
            )

    def split_osm_edge(self, directed: list[tuple], positions: list[float]) -> list:
        """OSM 구간(양방향 edge 들)을 첫 edge 방향 거리 positions 에서 나눈다.

        나눈 점 노드 번호를 돌려준다. 고도는 양 끝 노드 사이 선형, 경사는 원래 값.
        """
        a, b, k = directed[0]
        line = self.edge_line(a, b, self.graph.edges[a, b, k])
        names = []
        for at in positions:
            q = line.interpolate(at)
            lon, lat = self.to_lonlat(q.x, q.y)
            t = at / line.length
            ends = self.graph.nodes[a]["elevation"], self.graph.nodes[b]["elevation"]
            n = self.new_node_id()
            self.graph.add_node(
                n, x=lon, y=lat, elevation=ends[0] * (1 - t) + ends[1] * t
            )
            self.split_nodes.add(n)
            names.append(n)
        chain = [a, *names, b]
        cut_at = [0.0, *positions, line.length]
        for x, y, kk in directed:
            data = dict(self.graph.edges[x, y, kk])
            forward = x == a
            nodes_seq = chain if forward else chain[::-1]
            at_seq = cut_at if forward else [line.length - at for at in cut_at[::-1]]
            path = line if forward else LineString(list(line.coords)[::-1])
            self.graph.remove_edge(x, y, kk)
            for (s0, s1), (n0, n1) in zip(
                zip(at_seq, at_seq[1:], strict=False),
                zip(nodes_seq, nodes_seq[1:], strict=False),
                strict=True,
            ):
                piece = substring(path, s0, s1)
                share = piece.length / line.length
                self.graph.add_edge(
                    n0,
                    n1,
                    **{
                        **data,
                        "geometry": self.lonlat(piece),
                        "length": data["length"] * share,
                    },
                )
        return names

    # 단계

    def find_covered_roads(self) -> None:
        """인도 링크가 나란히 덮은 큰 도로 중심선에 sidewalk_separate 를 표시한다."""
        s = self.s
        minx, miny, maxx, maxy = (
            min(line.bounds[0] for line in self.links),
            min(line.bounds[1] for line in self.links),
            max(line.bounds[2] for line in self.links),
            max(line.bounds[3] for line in self.links),
        )
        big_roads = set(s["big_roads"])
        segments: dict[tuple, list[tuple]] = defaultdict(list)
        segment_line: dict[tuple, LineString] = {}
        outside: set[tuple] = set()
        for u, v, k, data in self.graph.edges(keys=True, data=True):
            data["sidewalk_separate"] = False
            if not highways(data) & big_roads:
                continue
            key = segment_key(u, v, data)
            if key in outside:
                continue
            segments[key].append((u, v, k))
            if key in segment_line:
                continue
            line = self.edge_line(u, v, data)
            x0, y0, x1, y1 = line.bounds
            if x1 < minx or x0 > maxx or y1 < miny or y0 > maxy:
                outside.add(key)
                segments.pop(key)
                continue
            segment_line[key] = line

        self.used_links: set[int] = set()
        covered_lines = []
        covered_edges: set[tuple] = set()
        for key, line in segment_line.items():
            near = self.parallel_links(line)
            if near is None:
                continue
            self.used_links |= near
            covered_lines.append(line)
            covered_edges.update(segments[key])
        for u, v, k in covered_edges:
            self.graph.edges[u, v, k]["sidewalk_separate"] = True
        self.covered_edges = covered_edges
        self.covered_lines = covered_lines
        self.covered_tree = STRtree(covered_lines) if covered_lines else None
        self.centerline_nodes = {n for u, v, _ in covered_edges for n in (u, v)}
        self.report.update(
            big_segments=len(segment_line),
            covered_segments=len(covered_lines),
            covered_km=round(sum(line.length for line in covered_lines) / 1000, 2),
        )

    def parallel_links(self, line: LineString) -> set[int] | None:
        """중심선을 min_coverage 이상 나란히 덮는 인도 링크 번호. 모자라면 None."""
        s = self.s
        samples = max(1, int(line.length // s["sample_m"]))
        covered = 0
        near: set[int] = set()
        for i in range(samples):
            at = (i + 0.5) * line.length / samples
            p = line.interpolate(at)
            road_dir = direction(line, at)
            hit = False
            for idx in self.link_tree.query(p.buffer(s["sidewalk_max_m"])):
                link = self.links[idx]
                if link.distance(p) > s["sidewalk_max_m"]:
                    continue
                link_dir = direction(link, link.project(p))
                if within_deg(road_dir, link_dir, s["parallel_deg"]):
                    hit = True
                    near.add(int(idx))
            covered += hit
        return near if covered / samples >= s["min_coverage"] else None

    def plan_connections(self) -> None:
        """교차로 노드·골목 → 인도 연결점, 링크 끝 → 다른 링크 연결점을 정한다."""
        self.used = sorted(self.used_links)
        self.used_tree = STRtree([self.links[i] for i in self.used])
        self.splits: dict[int, set[float]] = defaultdict(set)
        # (그래프 노드, 링크 번호, 링크 위 거리, 차도 위인지)
        self.connectors: list[tuple] = []
        alley_cuts: dict[tuple, list[tuple]] = defaultdict(list)
        crossings = [
            n
            for n in self.centerline_nodes
            if any(
                (a, b, k) not in self.covered_edges
                for a, b, k in [
                    *self.graph.out_edges(n, keys=True),
                    *self.graph.in_edges(n, keys=True),
                ]
            )
        ]
        for n in crossings:
            self.connect_crossing(n, alley_cuts)
        self.split_alleys(crossings, alley_cuts)
        self.snap_link_ends()
        self.report["crossing_nodes"] = len(crossings)

    def nearest_by_side(
        self,
        p: Point,
        side: Callable[[Point], int],
        allowed: Callable[[Point], bool] = lambda c: True,
    ) -> dict[int, tuple[float, int, float]]:
        """p 에서 connect_max_m 안의 가장 가까운 인도 링크 점. side(c) 값마다 하나."""
        limit = self.s["connect_max_m"]
        best: dict[int, tuple[float, int, float]] = {}
        for j in self.used_tree.query(p.buffer(limit)):
            idx = self.used[int(j)]
            link = self.links[idx]
            at = link.project(p)
            c = link.interpolate(at)
            dist = c.distance(p)
            if dist > limit or not allowed(c):
                continue
            key = side(c)
            if key not in best or dist < best[key][0]:
                best[key] = (dist, idx, round(at, 2))
        return best

    def connect_crossing(self, n: Hashable, alley_cuts: dict) -> None:
        s = self.s
        p = self.node_point(n)
        assert self.covered_tree is not None
        road = self.covered_lines[int(self.covered_tree.nearest(p))]
        road_dir = direction(road, road.project(p))
        local_roads = [
            self.covered_lines[int(i)]
            for i in self.covered_tree.query(p.buffer(s["alley_max_m"]))
        ]

        def road_side(c: Point) -> int:
            return side_of(p, road_dir, c)

        def road_distance(c: Point) -> float:
            return min(line.distance(c) for line in local_roads)

        def across(c: Point) -> bool:
            # 도로와 비스듬한 선은 다른 길의 인도로 간다.
            dx, dy = c.x - p.x, c.y - p.y
            norm = math.hypot(dx, dy) or 1.0
            return not within_deg(
                road_dir, (dx / norm, dy / norm), s["crossing_min_deg"]
            )

        best = self.nearest_by_side(p, road_side, allowed=across)
        alley_sides: set[int] = set()
        for _, v, k, data in self.graph.out_edges(n, keys=True, data=True):
            if (n, v, k) in self.covered_edges:
                continue
            line = self.edge_line(n, v, data)
            side = road_side(line.interpolate(min(s["alley_arm_m"], line.length)))
            if side not in best:
                continue
            _, idx, at = best[side]
            offset = road_distance(self.links[idx].interpolate(at))
            step = s["alley_step_m"]
            along = next(
                (
                    float(d)
                    for d in np.arange(
                        step, min(line.length - step, s["alley_max_m"]), step
                    )
                    if road_distance(line.interpolate(d)) >= offset
                ),
                None,
            )
            # 골목 첫 구간이 인도까지 못 미치면, 도로에서 멀어진 구간 끝 노드를 잇는다.
            end = Point(line.coords[-1])
            if along is None and road_distance(end) < offset / 2:
                continue
            q = end if along is None else line.interpolate(along)
            alley_dir = direction(line, line.length if along is None else along)
            near = self.nearest_by_side(
                q,
                lambda c, q=q, d=alley_dir: side_of(q, d, c),
                allowed=lambda c, side=side: road_side(c) == side,
            )
            if not near:
                continue
            if along is None:
                for _, near_idx, near_at in near.values():
                    self.splits[near_idx].add(near_at)
                    self.connectors.append((v, near_idx, near_at, False))
            else:
                alley_cuts[segment_key(n, v, data)].append(
                    (n, along, list(near.values()))
                )
            alley_sides.add(side)
        for side, (_, idx, at) in best.items():
            if side in alley_sides:
                continue
            self.splits[idx].add(at)
            self.connectors.append((n, idx, at, True))

    def split_alleys(self, crossings: list, alley_cuts: dict) -> None:
        segment_edges: dict[tuple, list[tuple]] = defaultdict(list)
        for n in crossings:
            for u, v, k, data in [
                *self.graph.out_edges(n, keys=True, data=True),
                *self.graph.in_edges(n, keys=True, data=True),
            ]:
                key = segment_key(u, v, data)
                if key in alley_cuts and (u, v, k) not in segment_edges[key]:
                    segment_edges[key].append((u, v, k))
        count = 0
        for key, cuts in alley_cuts.items():
            a, b, k = segment_edges[key][0]
            length = self.edge_line(a, b, self.graph.edges[a, b, k]).length
            positions = merge_cuts(
                [(along if n == a else length - along, near) for n, along, near in cuts]
            )
            names = self.split_osm_edge(segment_edges[key], [at for at, _ in positions])
            count += len(names)
            for name, (_, nears) in zip(names, positions, strict=True):
                for _, idx, link_at in nears[0]:
                    self.splits[idx].add(link_at)
                    self.connectors.append((name, idx, link_at, False))
        self.report["alley_points"] = count

    def snap_link_ends(self) -> None:
        """다른 링크 중간에 snap_m 안으로 닿는 링크 끝을 그 점에 잇는다."""
        snap = self.s["snap_m"]
        self.snaps: list[tuple[tuple[float, float], int, float]] = []
        for idx in self.used:
            link = self.links[idx]
            for end in (Point(link.coords[0]), Point(link.coords[-1])):
                for j in self.used_tree.query(end.buffer(snap)):
                    other = self.used[int(j)]
                    o = self.links[other]
                    at = o.project(end)
                    if (
                        other == idx
                        or o.distance(end) > snap
                        or at < snap
                        or at > o.length - snap
                    ):
                        continue
                    self.splits[other].add(round(at, 2))
                    self.snaps.append(((end.x, end.y), other, round(at, 2)))

    def insert_links(self) -> None:
        """인도 링크를 연결점에서 나눠 넣고 연결선을 잇는다."""
        split_node: dict[tuple[int, float], int] = {}
        added_m = 0.0
        for idx in self.used:
            link = self.links[idx]
            cuts = sorted(
                {
                    0.0,
                    link.length,
                    *(min(max(a, 0.0), link.length) for a in self.splits[idx]),
                }
            )
            for a, b in zip(cuts, cuts[1:], strict=False):
                if b - a < MIN_LINK_PIECE_M:
                    continue
                piece = substring(link, a, b)
                start = self.sidewalk_node(*piece.coords[0])
                end = self.sidewalk_node(*piece.coords[-1])
                split_node[(idx, a)] = start
                split_node[(idx, b)] = end
                if start != end:
                    self.add_edge(start, end, piece, "footway")
                    added_m += piece.length

        def target(idx: int, at: float) -> int | None:
            link = self.links[idx]
            found = split_node.get((idx, min(max(at, 0.0), link.length)))
            if found is None:
                c = link.interpolate(at)
                key = (
                    round(c.x / self.s["node_grid_m"]),
                    round(c.y / self.s["node_grid_m"]),
                )
                found = self.grid.get(key)
            return found

        connector_m = 0.0
        pending = [*self.connectors]
        pending += [
            (self.sidewalk_node(*xy), idx, at, False) for xy, idx, at in self.snaps
        ]
        for n, idx, at, on_road in pending:
            t = target(idx, at)
            if t is None or n == t or n not in self.graph:
                continue
            line = LineString([self.node_point(n).coords[0], self.sidewalk_nodes[t]])
            self.add_edge(n, t, line, "footway", sidewalk_separate=on_road)
            connector_m += line.length
        self.report.update(
            sidewalk_links=len(self.used),
            sidewalk_km=round(added_m / 1000, 2),
            connectors=len(pending),
            connector_km=round(connector_m / 1000, 2),
        )

    def connect_dangling(self) -> None:
        """홀로 끝난 인도 끝을 가까운 OSM 길 위 점(없으면 노드)에 잇는다."""
        limit = self.s["dangling_max_m"]
        osm_nodes = [
            n
            for n in self.graph.nodes
            if n not in self.sidewalk_nodes and self.graph.degree(n) > 0
        ]
        node_m = {n: self.node_point(n) for n in osm_nodes}
        osm_points = [node_m[n] for n in osm_nodes]
        osm_tree = STRtree(osm_points)
        self.osm_nodes, self.osm_tree = osm_nodes, osm_tree
        xs = [x for x, _ in self.sidewalk_nodes.values()]
        ys = [y for _, y in self.sidewalk_nodes.values()]
        bounds = (min(xs) - limit, min(ys) - limit, max(xs) + limit, max(ys) + limit)
        segments: dict[tuple, list[tuple]] = defaultdict(list)
        for u, v, k, data in self.graph.edges(keys=True, data=True):
            osmid = data.get("osmid")
            if data.get("sidewalk_separate") or u not in node_m or v not in node_m:
                continue
            if isinstance(osmid, int) and osmid < 0:
                continue
            pu, pv = node_m[u], node_m[v]
            if (
                max(pu.x, pv.x) < bounds[0]
                or min(pu.x, pv.x) > bounds[2]
                or max(pu.y, pv.y) < bounds[1]
                or min(pu.y, pv.y) > bounds[3]
            ):
                continue
            segments[segment_key(u, v, data)].append((u, v, k))
        keys = list(segments)
        lines = [
            self.edge_line(*segments[key][0][:2], self.graph.edges[segments[key][0]])
            for key in keys
        ]
        segment_tree = STRtree(lines)
        count = 0
        cuts: dict[int, list[tuple[float, int]]] = defaultdict(list)
        for n, (x, y) in list(self.sidewalk_nodes.items()):
            if self.graph.degree(n) != 2:  # 양방향 edge 2개 = 이웃 1개
                continue
            p = Point(x, y)
            j = segment_tree.nearest(p) if lines else None
            if j is not None and lines[int(j)].distance(p) <= limit:
                line = lines[int(j)]
                at = line.project(p)
                a, b, _ = segments[keys[int(j)]][0]
                if at < MIN_PIECE_M or at > line.length - MIN_PIECE_M:
                    end = a if at < MIN_PIECE_M else b
                    self.add_edge(
                        n,
                        end,
                        LineString([(x, y), node_m[end].coords[0]]),
                        "footway",
                        sidewalk_separate=end in self.centerline_nodes,
                    )
                else:
                    cuts[int(j)].append((at, n))
                count += 1
                continue
            j = osm_tree.nearest(p)
            if j is None or osm_points[int(j)].distance(p) > limit:
                continue
            end = osm_nodes[int(j)]
            self.add_edge(
                n,
                end,
                LineString([(x, y), osm_points[int(j)].coords[0]]),
                "footway",
                sidewalk_separate=end in self.centerline_nodes,
            )
            count += 1
        for j, edge_cuts in cuts.items():
            positions = merge_cuts(edge_cuts)
            names = self.split_osm_edge(segments[keys[j]], [at for at, _ in positions])
            for name, (_, ends) in zip(names, positions, strict=True):
                q = self.node_point(name)
                for end in ends:
                    self.add_edge(
                        end,
                        name,
                        LineString([self.sidewalk_nodes[end], q.coords[0]]),
                        "footway",
                    )
        self.report["dangling_connectors"] = count

    def finish(self) -> None:
        """새 인도 노드 고도(DEM, 빈 칸이면 가까운 OSM 노드)와 새 길 경사를 정한다."""
        nodes = list(self.sidewalk_nodes)
        values = self.elevation_of(
            [(self.graph.nodes[n]["x"], self.graph.nodes[n]["y"]) for n in nodes]
        )
        for n, value in zip(nodes, values, strict=True):
            if value is None:
                j = self.osm_tree.nearest(Point(self.sidewalk_nodes[n]))
                value = self.graph.nodes[self.osm_nodes[int(j)]]["elevation"]
            self.graph.nodes[n]["elevation"] = float(value)
        for u, v, data in self.graph.edges(data=True):
            osmid = data.get("osmid")
            if isinstance(osmid, int) and osmid < 0:
                rise = (
                    self.graph.nodes[v]["elevation"] - self.graph.nodes[u]["elevation"]
                )
                length = data["length"]
                data["grade"] = (
                    round(rise / length, GRADE_DIGITS) if length > 0 else 0.0
                )

    def run(self) -> dict[str, Any]:
        if not self.links:
            return self.report
        self.find_covered_roads()
        if not self.covered_lines:
            return self.report
        self.plan_connections()
        self.insert_links()
        self.connect_dangling()
        self.finish()
        return self.report


def merge_cuts(cuts: list[tuple[float, Any]]) -> list[tuple[float, list]]:
    """거리순으로 놓고 MIN_PIECE_M 안에 붙은 자르는 점은 하나로 합친다."""
    merged: list[tuple[float, list]] = []
    for at, item in sorted(cuts, key=lambda c: c[0]):
        if merged and at - merged[-1][0] < MIN_PIECE_M:
            merged[-1][1].append(item)
        else:
            merged.append((at, [item]))
    return merged


def dem_elevations(dem_path: Path) -> ElevationOf:
    def elevation_of(points: Sequence[tuple[float, float]]) -> list[float | None]:
        if not points:
            return []
        with rasterio.open(dem_path) as dem:
            xs, ys = warp_transform(
                "EPSG:4326", dem.crs, [p[0] for p in points], [p[1] for p in points]
            )
            values = [v[0] for v in dem.sample(zip(xs, ys, strict=True), masked=True)]
        return [None if np.ma.is_masked(v) else float(v) for v in values]

    return elevation_of


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)
    settings = config["sidewalks"]
    walknet_dir = data_path(config["walknet"]["output_dir"])
    district_files = [
        walknet_dir / f"{name}.json.gz" for name in config["walknet"]["districts"]
    ]
    source = data_path(config["barriers"]["output"])
    dem_path = data_path(config["dem"]["output"])
    output = data_path(settings["output"])
    require_files(source, dem_path, *district_files)

    started = time.time()
    rows = []
    for path in district_files:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            rows.extend(json.load(f))
    links = walknet_links(rows, settings["excluded_flags"])
    bool_tags = export_step.BOOL_TAGS
    graph = ox.load_graphml(
        source, edge_dtypes={tag: export_step.parse_bool for tag in bool_tags}
    )
    print(
        f"인도 링크 {len(links)}개, 그래프 구간 {graph.number_of_edges()}개", flush=True
    )
    report = SidewalkBuilder(
        graph,
        links,
        settings,
        config["barriers"]["metric_crs"],
        dem_elevations(dem_path),
    ).run()
    print(report, flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, output)
    print(f"→ {output} ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
