"""S-DoT 유동인구 센서 설치 위치를 백엔드용 sdot_sensors.json 으로 내보낸다.

실행: pipeline/ 에서 uv run python steps/05_export_sdot_sensors.py
- 입력: 서울 열린데이터광장의 '유동인구 설치 위치정보' xlsx (raw/sdot/)
- 출력: sensors [{code, lon, lat, address}]
  code 는 실시간 API(sDoTPeople) 응답의 SERIAL 을 정수로 바꾼 값과 같다.
그래프(00~04 단계)와 관계가 없어서 run_all.py 에 넣지 않고 따로 실행한다.
"""

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from common import CONFIG_PATH, data_path, load_config, repo_path, require_files

CODE_COLUMN = "방문자 센서코드"
ADDRESS_COLUMN = "주소"
LAT_COLUMN = "위도"
LON_COLUMN = "경도"
COORD_DIGITS = 6  # 약 0.1m


def parse_sensors(
    rows: Iterable[tuple[Any, ...]], bounds: dict[str, float]
) -> list[dict[str, Any]]:
    """첫 행의 열 이름으로 센서를 읽는다. 위도·경도가 문자열인 행도 있다."""
    iterator = iter(rows)
    header = list(next(iterator))
    column = {name: header.index(name) for name in header if name}
    sensors = []
    for row in iterator:
        if row[column[CODE_COLUMN]] is None:
            continue
        code = int(row[column[CODE_COLUMN]])
        lat = float(row[column[LAT_COLUMN]])
        lon = float(row[column[LON_COLUMN]])
        if not (
            bounds["min_lat"] <= lat <= bounds["max_lat"]
            and bounds["min_lon"] <= lon <= bounds["max_lon"]
        ):
            raise SystemExit(f"센서 {code} 의 좌표({lat}, {lon})가 서울 범위 밖입니다.")
        sensors.append(
            {
                "code": code,
                "lon": round(lon, COORD_DIGITS),
                "lat": round(lat, COORD_DIGITS),
                "address": str(row[column[ADDRESS_COLUMN]]).strip(),
            }
        )
    codes = [sensor["code"] for sensor in sensors]
    if len(codes) != len(set(codes)):
        raise SystemExit("센서 코드가 중복됩니다.")
    return sensors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["sdot"]
    source = data_path(config["source"])
    output = repo_path(config["output"])
    require_files(source)

    workbook = load_workbook(source, read_only=True, data_only=True)
    sensors = parse_sensors(workbook.worksheets[0].iter_rows(values_only=True), config)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"sensors": sensors}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"센서 {len(sensors)}개 → {output}", flush=True)


if __name__ == "__main__":
    main()
