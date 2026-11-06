"""수집 DB(backend 수집기)의 S-DoT 유동인구를 realtime.parquet 한 파일로 내보낸다.

실행: pipeline/ 에서 uv run python steps/16_export_sdot_realtime.py
- 입력: 수집 DB 의 sdot_readings 표(backend/app/collector). 접속 주소는 pipeline/.env 의
  COLLECTOR_DATABASE_URL 이다(backend 와 같은 값, postgresql+psycopg://… 도 된다).
- 출력: interim/sdot/realtime.parquet 과 realtime_report.json
  열: history.parquet(06 단계)과 같다. sensor_code, measured_at, visitor_count, region,
  district, dong, source_file
  measured_at 은 한국 시각(시간대 없이)이다. history 의 측정시간과 같은 기준이다.
  source_file 은 수집 DB 에서 왔다는 표시(config 의 source_name)다.
13 단계가 history 와 이 파일을 합친다. 학습셋을 갱신할 때는 16 → 13 순서로 돌린다.
그래프(00~04 단계)와 관계가 없어서 run_all.py 에 넣지 않고 따로 실행한다.
"""

import argparse
import json
import os
import sys
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from common import CONFIG_PATH, data_path, load_config

PARQUET_COMPRESSION = "zstd"
URL_ENV = "COLLECTOR_DATABASE_URL"
# SQLAlchemy 주소(postgresql+psycopg://)를 psycopg 가 읽는 주소로 바꾼다.
DRIVER_PREFIXES = ("postgresql+psycopg://", "postgres+psycopg://")
# history.parquet 과 같은 열과 타입
SCHEMA = pa.schema(
    [
        ("sensor_code", pa.int32()),
        ("measured_at", pa.timestamp("ms")),
        ("visitor_count", pa.int32()),
        ("region", pa.string()),
        ("district", pa.string()),
        ("dong", pa.string()),
        ("source_file", pa.string()),
    ]
)
# 한국 시각으로 바꿔 시간대 없이 받는다.
# 표 이름·열 이름은 backend/app/collector/models.py 와 같다.
QUERY = """
SELECT sensor_code, measured_at AT TIME ZONE %(timezone)s, visitor_count,
       region, district, dong
FROM sdot_readings
ORDER BY sensor_code, measured_at
"""


def to_libpq_url(url: str) -> str:
    """SQLAlchemy 드라이버 표시를 뺀 PostgreSQL 주소."""
    for prefix in DRIVER_PREFIXES:
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def to_table(
    rows: Iterable[tuple[int, datetime, int, str | None, str | None, str | None]],
    source_name: str,
) -> pa.Table:
    """DB 행 (sensor_code, 한국 시각, visitor_count, region, district, dong) → 표."""
    columns: dict[str, list[Any]] = {name: [] for name in SCHEMA.names}
    for code, measured_at, count, region, district, dong in rows:
        columns["sensor_code"].append(code)
        columns["measured_at"].append(measured_at)
        columns["visitor_count"].append(count)
        columns["region"].append(region)
        columns["district"].append(district)
        columns["dong"].append(dong)
        columns["source_file"].append(source_name)
    return pa.table(columns, schema=SCHEMA)


def read_rows(
    url: str, config: dict[str, Any]
) -> list[tuple[int, datetime, int, str | None, str | None, str | None]]:
    with psycopg.connect(
        to_libpq_url(url), connect_timeout=config["connect_timeout_s"]
    ) as conn:
        cursor = conn.execute(QUERY, {"timezone": config["timezone"]})
        return cursor.fetchall()


def make_report(table: pa.Table) -> dict[str, Any]:
    if table.num_rows == 0:
        return {"rows": 0, "sensors": 0}
    return {
        "rows": table.num_rows,
        "sensors": len(set(table["sensor_code"].to_pylist())),
        "first_measured_at": pc.min(table["measured_at"]).as_py().isoformat(),
        "last_measured_at": pc.max(table["measured_at"]).as_py().isoformat(),
        "missing_district": int(table["district"].null_count),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["sdot_realtime"]
    url = os.environ.get(URL_ENV, "").strip().strip('"')
    if not url:
        print(f"pipeline/.env 의 {URL_ENV} 가 비어 있습니다.")
        return 1

    started = time.time()
    try:
        rows = read_rows(url, config)
    except psycopg.Error as error:
        # 예외 문구에 접속 주소가 섞일 수 있어 종류만 남긴다.
        print(f"수집 DB 읽기 실패 ({type(error).__name__})")
        return 1
    table = to_table(rows, config["source_name"])
    output = data_path(config["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, output, compression=PARQUET_COMPRESSION)
    report = make_report(table)
    data_path(config["report"]).write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"행 {report['rows']:,}, 센서 {report['sensors']}개, "
        f"{report.get('first_measured_at')} ~ {report.get('last_measured_at')} "
        f"→ {output} ({time.time() - started:.0f}s)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
