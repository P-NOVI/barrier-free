"""지하철역 엘리베이터 위치 CSV(cp949)를 지도용 elevators.json 으로 바꾼다.

실행: uv run --project backend python data/sample/make_elevators.py <CSV 경로>
- 임시 스크립트다. pipeline 단계와 /api/elevators 가 생기면 이 파일과 JSON 을 지운다.
"""

import csv
import json
import re
import sys
from pathlib import Path

ENCODING = "cp949"
OUTPUT = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "public"
    / "data"
    / "elevators.json"
)
WKT_POINT = re.compile(r"^POINT\((?P<lng>-?\d+\.?\d*) (?P<lat>-?\d+\.?\d*)\)$")
SEOUL_LAT = (37.0, 38.0)
SEOUL_LNG = (126.0, 128.0)

COLUMNS = {
    "wkt": "노드 WKT",
    "id": "노드 ID",
    "node_type": "노드 유형 코드",
    "district": "시군구명",
    "station": "지하철역명",
}


def parse_row(row: dict[str, str]) -> dict[str, object]:
    match = WKT_POINT.match(row[COLUMNS["wkt"]].strip())
    if match is None:
        raise ValueError(f"좌표 형식이 다릅니다: {row[COLUMNS['wkt']]!r}")
    lng, lat = float(match["lng"]), float(match["lat"])
    if not (SEOUL_LAT[0] < lat < SEOUL_LAT[1] and SEOUL_LNG[0] < lng < SEOUL_LNG[1]):
        raise ValueError(f"서울 범위 밖 좌표입니다: {lng}, {lat}")
    return {
        "id": row[COLUMNS["id"]],
        "station": row[COLUMNS["station"]].strip(),
        "district": row[COLUMNS["district"]].strip(),
        "nodeType": int(row[COLUMNS["node_type"]]),
        "position": [lng, lat],
    }


def convert(csv_path: Path) -> list[dict[str, object]]:
    with csv_path.open(encoding=ENCODING, newline="") as f:
        return [parse_row(row) for row in csv.DictReader(f)]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    elevators = convert(Path(sys.argv[1]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(elevators, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(elevators)}건 -> {OUTPUT}")


if __name__ == "__main__":
    main()
