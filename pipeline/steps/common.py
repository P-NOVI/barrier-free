"""pipeline 단계 공통: 설정 읽기, 데이터 경로, Overpass 요청과 영역 고리, 거리.

데이터 경로는 pipeline/.env 의 DATA_DIR(Google Drive 공유 폴더 등) 기준이고,
없으면 저장소의 data/ 를 쓴다. 서버가 읽는 결과(data/processed)는 저장소 기준이다.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from dotenv import load_dotenv

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_DIR.parent
CONFIG_PATH = PIPELINE_DIR / "config.yaml"
ENV_PATH = PIPELINE_DIR / ".env"
# Overpass 가 붐비거나 잠깐 멈췄을 때 돌려주는 상태 코드. 기다렸다 다시 보낸다.
OVERPASS_BUSY = {429, 502, 503, 504}
COORD_DIGITS = 6  # 약 0.1m
# 닫힌 고리의 최소 점 수(처음 점이 끝에 한 번 더 온다)
MIN_RING_POINTS = 4
EARTH_RADIUS_M = 6_371_000

LngLat = tuple[float, float]

load_dotenv(ENV_PATH)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def data_dir() -> Path:
    """공유 데이터 폴더. DATA_DIR 이 비어 있으면 저장소의 data/."""
    value = os.environ.get("DATA_DIR", "").strip().strip('"')
    return Path(value).expanduser() if value else REPO_ROOT / "data"


def data_path(relative: str) -> Path:
    """config.yaml 의 데이터 경로(raw/…, interim/…) → 실제 경로."""
    return data_dir() / relative


def repo_path(relative: str) -> Path:
    """config.yaml 의 저장소 경로(data/processed/…) → 실제 경로."""
    return REPO_ROOT / relative


def fetch_overpass(config: dict[str, Any], query: str, timeout_s: int) -> dict:
    """config.yaml 의 overpass 항목으로 Overpass API 에 query 를 보낸다."""
    body = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(
        config["url"], data=body, headers={"User-Agent": config["user_agent"]}
    )
    for attempt in range(1, config["attempts"] + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                data = json.load(response)
            break
        except urllib.error.HTTPError as error:
            if error.code not in OVERPASS_BUSY or attempt == config["attempts"]:
                raise
            print(f"Overpass {error.code}, 다시 보냄 ({attempt})", flush=True)
            time.sleep(config["retry_wait_s"])
    if not data.get("elements"):
        raise SystemExit("Overpass 응답이 비었습니다. 지역 이름과 서버를 확인하세요.")
    return data


def point(node: dict[str, Any]) -> LngLat:
    return (round(node["lon"], COORD_DIGITS), round(node["lat"], COORD_DIGITS))


def join_rings(segments: Iterable[list[LngLat]]) -> list[list[LngLat]]:
    """multipolygon 의 outer way 조각들을 끝점끼리 이어 닫힌 고리로 만든다.

    닫히지 않는 조각(데이터 오류, 범위 밖에서 잘린 것)은 버린다.
    """
    pending = [list(segment) for segment in segments if len(segment) >= 2]
    rings = []
    while pending:
        ring = pending.pop()
        while ring[0] != ring[-1]:
            for i, segment in enumerate(pending):
                if segment[0] == ring[-1]:
                    ring += segment[1:]
                elif segment[-1] == ring[-1]:
                    ring += segment[-2::-1]
                else:
                    continue
                pending.pop(i)
                break
            else:
                break
        if ring[0] == ring[-1] and len(ring) >= MIN_RING_POINTS:
            rings.append(ring)
    return rings


def outer_ways(element: dict[str, Any]) -> list[dict[str, Any]]:
    """multipolygon relation 의 outer way 멤버."""
    return [
        m for m in element["members"] if m["type"] == "way" and m["role"] == "outer"
    ]


def outer_rings(element: dict[str, Any]) -> list[list[LngLat]]:
    """Overpass(out geom) 닫힌 way 나 multipolygon 의 바깥 고리. 안뜰은 뺀다."""
    if element["type"] == "way":
        ring = [point(g) for g in element.get("geometry", [])]
        rings = [ring] if ring and ring[0] == ring[-1] else []
    elif element["type"] == "relation":
        rings = join_rings(
            [point(g) for g in m["geometry"]]
            for m in outer_ways(element)
            if m.get("geometry")
        )
    else:
        return []
    return [ring for ring in rings if len(ring) >= MIN_RING_POINTS]


def require_files(*paths: Path) -> None:
    """입력 파일이 없으면 원인과 할 일을 알려 주고 멈춘다."""
    missing = [path for path in paths if not path.exists()]
    if not missing:
        return
    lines = "\n".join(f"  - {path}" for path in missing)
    raise SystemExit(
        f"필요한 파일이 없습니다.\n{lines}\n"
        f"데이터 폴더: {data_dir()}\n"
        "- 공유 폴더를 쓰면 Google Drive 데스크톱이 켜져 있는지, "
        "pipeline/.env 의 DATA_DIR 이 맞는지 확인하세요.\n"
        "- 앞 단계 결과가 없으면 steps/run_all.py 로 앞 단계부터 실행하세요."
    )


def distance_m(lon1, lat1, lon2, lat2):
    """두 점(경도, 위도) 사이 대권 거리(m). numpy 배열을 넣으면 배열로 돌려준다."""
    lon1, lat1, lon2, lat2 = (np.radians(v) for v in (lon1, lat1, lon2, lat2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))
