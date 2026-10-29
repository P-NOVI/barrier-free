"""테스트용 10×10 격자 그래프(graph.json)를 만든다.

실행: uv run --project backend python data/sample/make_grid.py
"""

import json
import math
from pathlib import Path

ORIGIN_LON, ORIGIN_LAT = 126.9779, 37.5663
SIZE = 10
SPACING_M = 50.0
HILL_ROW, HILL_COL, HILL_HEIGHT_M, HILL_SIGMA_CELLS = 6, 6, 12.0, 1.5
BASE_ELEVATION_M = 30.0
STEPS = {((6, 3), (6, 4)), ((3, 6), (4, 6))}
NO_WALK = {((0, 4), (0, 5))}
NO_WHEELCHAIR = {((8, 1), (8, 2))}
OUTPUT = Path(__file__).with_name("graph.json")

LAT_PER_M = 1 / 111_320
LON_PER_M = 1 / (111_320 * math.cos(math.radians(ORIGIN_LAT)))


def node_id(row: int, col: int) -> int:
    return row * SIZE + col


def elevation(row: int, col: int) -> float:
    d2 = (row - HILL_ROW) ** 2 + (col - HILL_COL) ** 2
    return BASE_ELEVATION_M + HILL_HEIGHT_M * math.exp(-d2 / (2 * HILL_SIGMA_CELLS**2))


def main() -> None:
    nodes = [
        {
            "lon": round(ORIGIN_LON + col * SPACING_M * LON_PER_M, 7),
            "lat": round(ORIGIN_LAT + row * SPACING_M * LAT_PER_M, 7),
            "elevation": round(elevation(row, col), 2),
        }
        for row in range(SIZE)
        for col in range(SIZE)
    ]
    edges = []
    for row in range(SIZE):
        for col in range(SIZE):
            for a, b in (((row, col), (row, col + 1)), ((row, col), (row + 1, col))):
                if b[0] >= SIZE or b[1] >= SIZE:
                    continue
                u, v = node_id(*a), node_id(*b)
                steps = (a, b) in STEPS
                edges.append(
                    {
                        "id": len(edges),
                        "u": u,
                        "v": v,
                        "length": SPACING_M,
                        "grade": round(
                            (nodes[v]["elevation"] - nodes[u]["elevation"]) / SPACING_M,
                            4,
                        ),
                        "steps": steps,
                        "ramp": False,
                        "wheelchair_ok": not steps
                        and (a, b) not in NO_WHEELCHAIR
                        and (a, b) not in NO_WALK,
                        "walk_ok": (a, b) not in NO_WALK,
                    }
                )
    lines = [json.dumps(item, ensure_ascii=False) for item in nodes]
    edge_lines = [json.dumps(item, ensure_ascii=False) for item in edges]
    OUTPUT.write_text(
        '{\n"nodes": [\n'
        + ",\n".join(lines)
        + '\n],\n"edges": [\n'
        + ",\n".join(edge_lines)
        + "\n]\n}\n",
        encoding="utf-8",
    )
    print(f"{OUTPUT.name}: nodes {len(nodes)}, edges {len(edges)}")


if __name__ == "__main__":
    main()
