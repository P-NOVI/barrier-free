"""1:5000 등고선·표고점 shapefile → 5m DEM GeoTIFF.

실행: pipeline/ 에서 uv run python steps/00_build_dem.py
경로와 격자 설정은 pipeline/config.yaml 의 dem 항목을 쓴다.
"""

import argparse
import struct
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import yaml
from rasterio.transform import from_origin
from rasterio.warp import transform
from rasterio.windows import Window
from scipy.interpolate import griddata
from scipy.spatial import cKDTree

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_DIR.parent
CONFIG_PATH = PIPELINE_DIR / "config.yaml"

NODATA = -9999.0
SHP_HEADER_BYTES = 100
# dbf 높이 필드의 (레코드 안 시작 위치, 폭). 국토지리정보원 N3L_F001 · N3P_F002 기준
CONTOUR_HEIGHT_FIELD = (34 + 6, 19)
POINT_HEIGHT_FIELD = (34 + 19 + 8 + 9, 19)
# 타일 중심에서 모서리까지(반 변 × √2) 근사
SEARCH_RADIUS_FACTOR = 1.4143

Arrays = tuple[np.ndarray, np.ndarray, np.ndarray]


def dbf_column(path: Path, start: int, width: int) -> list[float]:
    """dbf 의 고정폭 숫자 필드 하나를 모든 레코드에서 읽는다."""
    with path.open("rb") as f:
        header = f.read(32)
        count, header_len, record_len = struct.unpack("<IHH", header[4:12])
        f.seek(header_len)
        return [
            float(f.read(record_len)[1 + start : 1 + start + width])
            for _ in range(count)
        ]


def shp_records(path: Path) -> Iterator[bytes]:
    with path.open("rb") as f:
        f.seek(SHP_HEADER_BYTES)
        while True:
            header = f.read(8)
            if len(header) < 8:
                return
            yield f.read(struct.unpack(">i", header[4:8])[0] * 2)


def read_contours(shp: Path, dbf: Path) -> Arrays:
    heights = dbf_column(dbf, *CONTOUR_HEIGHT_FIELD)
    xs, ys, zs = [], [], []
    for record, z in zip(shp_records(shp), heights, strict=True):
        part_count, point_count = struct.unpack("<2i", record[36:44])
        offset = 44 + 4 * part_count
        points = np.frombuffer(
            record[offset : offset + 16 * point_count], dtype="<f8"
        ).reshape(-1, 2)
        xs.append(points[:, 0])
        ys.append(points[:, 1])
        zs.append(np.full(point_count, z))
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)


def read_points(shp: Path, dbf: Path) -> Arrays:
    zs = np.array(dbf_column(dbf, *POINT_HEIGHT_FIELD))
    xy = np.array([struct.unpack("<2d", record[4:20]) for record in shp_records(shp)])
    return xy[:, 0], xy[:, 1], zs


def build_dem(
    contour_shp: Path,
    contour_dbf: Path,
    point_shp: Path,
    point_dbf: Path,
    output: Path,
    *,
    source_crs: str,
    target_crs: str,
    resolution: float,
    tile: float,
    buffer: float,
    max_gap: float,
) -> None:
    """5km 타일마다 주변 등고선·표고점으로 TIN 선형 보간해 GeoTIFF 로 쓴다."""
    started = time.time()
    cx, cy, cz = read_contours(contour_shp, contour_dbf)
    px, py, pz = read_points(point_shp, point_dbf)
    x = np.concatenate([cx, px])
    y = np.concatenate([cy, py])
    z = np.concatenate([cz, pz])
    x, y = (
        np.array(v) for v in transform(source_crs, target_crs, x.tolist(), y.tolist())
    )
    print(
        f"loaded {len(cx)} contour vertices + {len(px)} points, "
        f"reprojected to {target_crs} ({time.time() - started:.0f}s)",
        flush=True,
    )

    xmin = np.floor(x.min() / resolution) * resolution
    ymin = np.floor(y.min() / resolution) * resolution
    xmax = np.ceil(x.max() / resolution) * resolution
    ymax = np.ceil(y.max() / resolution) * resolution
    width = int((xmax - xmin) / resolution)
    height = int((ymax - ymin) / resolution)
    tree = cKDTree(np.column_stack([x, y]))
    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": 1,
        "dtype": "float32",
        "crs": target_crs,
        "transform": from_origin(xmin, ymax, resolution, resolution),
        "nodata": NODATA,
        "compress": "deflate",
        "predictor": 3,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "BIGTIFF": "IF_SAFER",
    }
    step = int(tile / resolution)
    tiles_x, tiles_y = -(-width // step), -(-height // step)
    print(f"grid {width}x{height} cells, {tiles_x}x{tiles_y} tiles", flush=True)

    with rasterio.open(output, "w", **profile) as dst:
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                col0, row0 = tx * step, ty * step
                w, h = min(step, width - col0), min(step, height - row0)
                gx = xmin + (col0 + np.arange(w) + 0.5) * resolution
                gy = ymax - (row0 + np.arange(h) + 0.5) * resolution
                grid_x, grid_y = np.meshgrid(gx, gy)
                out_tile = np.full((h, w), NODATA, dtype="float32")
                center = [(gx[0] + gx[-1]) / 2, (gy[0] + gy[-1]) / 2]
                idx = tree.query_ball_point(
                    center, r=tile / 2 * SEARCH_RADIUS_FACTOR + buffer
                )
                if len(idx) >= 3:
                    sel = np.array(idx)
                    sx, sy = x[sel], y[sel]
                    keep = (
                        (sx > gx[0] - buffer)
                        & (sx < gx[-1] + buffer)
                        & (sy > gy[-1] - buffer)
                        & (sy < gy[0] + buffer)
                    )
                    sel = sel[keep]
                    if len(sel) >= 3:
                        grid = griddata(
                            np.column_stack([x[sel], y[sel]]),
                            z[sel],
                            (grid_x, grid_y),
                            method="linear",
                        )
                        dist, _ = tree.query(
                            np.column_stack([grid_x.ravel(), grid_y.ravel()]),
                            distance_upper_bound=max_gap,
                        )
                        grid[np.isinf(dist).reshape(grid.shape)] = np.nan
                        ok = ~np.isnan(grid)
                        out_tile[ok] = grid[ok]
                dst.write(out_tile, 1, window=Window(col0, row0, w, h))
            print(
                f"row {ty + 1}/{tiles_y} done ({time.time() - started:.0f}s)",
                flush=True,
            )
    print("saved", output, flush=True)


def load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["dem"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)
    output = REPO_ROOT / config["output"]
    output.parent.mkdir(parents=True, exist_ok=True)
    build_dem(
        REPO_ROOT / config["contour_shp"],
        REPO_ROOT / config["contour_dbf"],
        REPO_ROOT / config["point_shp"],
        REPO_ROOT / config["point_dbf"],
        output,
        source_crs=config["source_crs"],
        target_crs=config["target_crs"],
        resolution=float(config["resolution_m"]),
        tile=float(config["tile_m"]),
        buffer=float(config["buffer_m"]),
        max_gap=float(config["max_gap_m"]),
    )


if __name__ == "__main__":
    main()
