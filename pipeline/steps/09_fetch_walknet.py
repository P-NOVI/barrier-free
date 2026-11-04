"""서울시 도보 네트워크(TbTraficWlkNet)를 자치구마다 받아 저장한다.

실행: pipeline/ 에서 uv run python steps/09_fetch_walknet.py
- 키는 pipeline/.env 의 SEOUL_API_KEY(서울 열린데이터광장 인증키, S-DoT 와 같은 키)다.
- 자치구 파일이 이미 있으면 건너뛴다. 다시 받으려면 그 파일을 지운다.
- 이 API 는 요청마다 행 순서가 달라서, 한 번 끝까지 받으면 행이 겹치고 빠진다
  (동작구 18,307행 중 고유 12,223행). 고유 행 수가 전체 행 수에 닿을 때까지
  처음부터 다시 받아 합친다.
"""

import argparse
import gzip
import json
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from common import CONFIG_PATH, data_path, load_config

Row = dict[str, Any]
# (시작 행, 끝 행) → (전체 행 수, 행 목록)
FetchPage = Callable[[int, int], tuple[int, list[Row]]]


def row_id(row: Row) -> tuple:
    if row["NODE_TYPE"] == "LINK":
        return ("LINK", row["LNKG_ID"])
    return ("NODE", row["NODE_ID"])


def fetch_all(fetch_page: FetchPage, page_size: int, max_passes: int) -> list[Row]:
    """고유 행이 전체 행 수에 닿을 때까지 처음부터 끝까지 다시 받아 합친다."""
    unique: dict[tuple, Row] = {}
    total = None
    for _ in range(max_passes):
        start = 1
        while total is None or start <= total:
            total, rows = fetch_page(start, start + page_size - 1)
            for row in rows:
                unique[row_id(row)] = row
            start += page_size
        if len(unique) >= total:
            return list(unique.values())
    raise SystemExit(
        f"{max_passes}번 받아도 고유 행 {len(unique)} / {total} 입니다. "
        "max_passes 를 늘리세요."
    )


def page_fetcher(config: dict[str, Any], key: str, district: str) -> FetchPage:
    def fetch_page(start: int, end: int) -> tuple[int, list[Row]]:
        url = (
            f"{config['url']}/{key}/json/{config['service']}/"
            f"{start}/{end}/{urllib.parse.quote(district)}"
        )
        for attempt in range(1, config["attempts"] + 1):
            try:
                with urllib.request.urlopen(url, timeout=config["timeout_s"]) as r:
                    data = json.load(r)[config["service"]]
                return data["list_total_count"], data["row"]
            except (OSError, KeyError, ValueError) as error:
                # 키가 담긴 URL 이 보이지 않게 오류 종류만 남긴다.
                if attempt == config["attempts"]:
                    raise SystemExit(
                        f"{district} {start}~{end}행 받기 실패: {type(error).__name__}"
                    ) from None
                time.sleep(config["retry_wait_s"])
        raise AssertionError("unreachable")

    return fetch_page


def district_path(config: dict[str, Any], district: str) -> Path:
    return data_path(config["walknet"]["output_dir"]) / f"{district}.json.gz"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)
    walknet = config["walknet"]
    key = os.environ.get("SEOUL_API_KEY", "").strip()
    if not key:
        raise SystemExit("pipeline/.env 에 SEOUL_API_KEY 가 없습니다.")

    for district in walknet["districts"]:
        output = district_path(config, district)
        if output.exists():
            print(f"{district}: 있음, 건너뜀", flush=True)
            continue
        started = time.time()
        rows = fetch_all(
            page_fetcher(walknet, key, district),
            walknet["page_size"],
            walknet["max_passes"],
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(output, "wt", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        print(f"{district}: {len(rows)}행 ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
