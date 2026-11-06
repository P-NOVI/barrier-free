"""지하철 승하차 자료(14 단계)의 역마다 좌표를 붙여 subway/stations.parquet 을 만든다.

실행: pipeline/ 에서 uv run python steps/15_build_subway_stations.py
- 입력: 서울 열린데이터광장 서울시 역사마스터 정보(subwayStationMaster),
        interim/subway/hourly.parquet (14 단계)
- 키는 pipeline/.env 의 SEOUL_API_KEY 다. 원본은 raw/subway/stations.json 으로 저장하고,
  있으면 다시 받지 않는다(역이 새로 생기면 그 파일을 지운다).
- 맞추는 방법(승하차 자료의 호선·역마다)
  1. 괄호 앞 이름이 같은 역사마스터 행을 찾는다("청량리(서울시립대입구)" → "청량리").
     역 이름이 바뀐 곳은 name_aliases 로 맞춘다(당고개 → 불암산).
  2. 그중 호선이 같은 행이 있으면 그 행만 쓴다. 두 자료에서 이름이 다른 호선은
     line_aliases 로 맞추고, 띄어쓰기는 빼고 비교한다.
  3. 남은 행이 same_place_m 안에 모여 있으면 좌표 평균을 쓴다. 흩어져 있으면(양평
     5호선·중앙선처럼 이름만 같은 다른 역) 정하지 않고 보고서에 남긴다.
- 출력: interim/subway/stations.parquet 과 stations_report.json
  열: line, station(14 단계와 같은 이름), lon, lat
그래프(00~04 단계)와 관계가 없어서 run_all.py 에 넣지 않고 따로 실행한다.
"""

import argparse
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from common import CONFIG_PATH, data_path, distance_m, load_config, require_files

OK_CODE = "INFO-000"
PARQUET_COMPRESSION = "zstd"
KEY_ENV = "SEOUL_API_KEY"
# 키 오류 같은 응답은 json 경로로 불러도 XML 로 온다.
XML_CODE = re.compile(r"<CODE>\s*([^<]+?)\s*</CODE>")

Row = dict[str, Any]


def parse_response(text: str, service: str, page_size: int) -> list[Row]:
    if text.lstrip().startswith("<"):
        match = XML_CODE.search(text)
        code = match.group(1) if match else "XML"
        raise SystemExit(f"응답 코드 {code}: {KEY_ENV} 를 확인하세요.")
    data = json.loads(text)
    body = data.get(service, data)
    result = body["RESULT"]
    if result["CODE"] != OK_CODE:
        raise SystemExit(f"응답 코드 {result['CODE']}: {result['MESSAGE']}")
    if body["list_total_count"] > page_size:
        raise SystemExit("역 수가 page_size 를 넘습니다. page_size 를 늘리세요.")
    return body["row"]


def fetch_master(config: dict[str, Any], key: str) -> list[Row]:
    url = f"{config['url']}/{key}/json/{config['service']}/1/{config['page_size']}/"
    for attempt in range(1, config["attempts"] + 1):
        try:
            with urllib.request.urlopen(url, timeout=config["timeout_s"]) as r:
                text = r.read().decode("utf-8")
            return parse_response(text, config["service"], config["page_size"])
        except (OSError, KeyError, ValueError) as error:
            # 키가 담긴 URL 이 보이지 않게 오류 종류만 남긴다.
            if attempt == config["attempts"]:
                raise SystemExit(
                    f"역사마스터 받기 실패: {type(error).__name__}"
                ) from None
            time.sleep(config["retry_wait_s"])
    raise AssertionError("unreachable")


def name_key(name: str) -> str:
    """괄호 앞 이름. '청량리(서울시립대입구)' → '청량리'"""
    return name.split("(")[0].strip()


def line_key(line: str, aliases: dict[str, str]) -> str:
    line = line.replace(" ", "")
    return aliases.get(line, line).replace(" ", "")


def match_stations(
    pairs: list[tuple[str, str]],
    master: list[Row],
    aliases: dict[str, dict[str, str]],
    same_place_m: float,
) -> tuple[list[Row], dict[str, list[str]]]:
    """승하차 자료의 (호선, 역) → 좌표. aliases 는 {"lines": {...}, "names": {...}}.

    반환: 좌표를 정한 행(line, station, lon, lat, matched_by), 못 정한 역
    (no_name: 같은 이름이 없음, scattered: 같은 이름이 흩어져 있음)
    """
    by_name: dict[str, list[Row]] = {}
    for row in master:
        by_name.setdefault(name_key(row["BLDN_NM"]), []).append(row)
    line_aliases = {k.replace(" ", ""): v for k, v in aliases["lines"].items()}
    name_aliases = aliases["names"]

    matched: list[Row] = []
    failed: dict[str, list[str]] = {"no_name": [], "scattered": []}
    for line, station in sorted(pairs):
        label = f"{line} {station}"
        name = name_key(station)
        candidates = by_name.get(name_aliases.get(name, name), [])
        if not candidates:
            failed["no_name"].append(label)
            continue
        wanted = line_key(line, line_aliases)
        same_line = [r for r in candidates if line_key(r["ROUTE"], {}) == wanted]
        rows = same_line or candidates
        lon = np.array([float(r["LOT"]) for r in rows])
        lat = np.array([float(r["LAT"]) for r in rows])
        spread = max(
            float(distance_m(lon[i], lat[i], lon[j], lat[j]))
            for i in range(len(rows))
            for j in range(len(rows))
        )
        if spread > same_place_m:
            failed["scattered"].append(label)
            continue
        matched.append(
            {
                "line": line,
                "station": station,
                "lon": float(lon.mean()),
                "lat": float(lat.mean()),
                "matched_by": "line" if same_line else "name",
            }
        )
    return matched, failed


def ridership_pairs(path: Path) -> list[tuple[str, str]]:
    table = pq.read_table(path, columns=["line", "station"])
    return sorted(set(zip(table["line"].to_pylist(), table["station"].to_pylist())))


def write_parquet(rows: list[Row], path: Path) -> None:
    schema = pa.schema(
        [
            ("line", pa.string()),
            ("station", pa.string()),
            ("lon", pa.float64()),
            ("lat", pa.float64()),
        ]
    )
    columns = {name: [row[name] for row in rows] for name in schema.names}
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table(columns, schema=schema), path, compression=PARQUET_COMPRESSION
    )


def make_report(
    pairs: list[tuple[str, str]],
    matched: list[Row],
    failed: dict[str, list[str]],
    master_rows: int,
) -> dict[str, Any]:
    return {
        "master_rows": master_rows,
        "ridership_stations": len(pairs),
        "matched": len(matched),
        "matched_by_line": sum(row["matched_by"] == "line" for row in matched),
        "matched_by_name": sum(row["matched_by"] == "name" for row in matched),
        "no_name": failed["no_name"],
        "scattered": failed["scattered"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["subway_stations"]
    ridership = data_path(config["ridership"])
    require_files(ridership)

    raw = data_path(config["raw"])
    if raw.exists():
        master = json.loads(raw.read_text(encoding="utf-8"))
    else:
        key = os.environ.get(KEY_ENV, "").strip()
        if not key:
            raise SystemExit(f"pipeline/.env 에 {KEY_ENV} 가 없습니다.")
        master = fetch_master(config, key)
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(json.dumps(master, ensure_ascii=False), encoding="utf-8")

    pairs = ridership_pairs(ridership)
    aliases = {"lines": config["line_aliases"], "names": config["name_aliases"]}
    matched, failed = match_stations(pairs, master, aliases, config["same_place_m"])
    output = data_path(config["output"])
    write_parquet(matched, output)
    report = make_report(pairs, matched, failed, len(master))
    data_path(config["report"]).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"역 {report['matched']}/{report['ridership_stations']} 좌표 정함, "
        f"이름 없음 {len(failed['no_name'])}, 흩어짐 {len(failed['scattered'])} "
        f"→ {output}"
    )


if __name__ == "__main__":
    main()
