"""로컬 SQLite 에 모아 둔 S-DoT 원본 행을 수집 DB의 sdot_readings 로 옮긴다(일회용).

실행: backend/ 에서 uv run python -m app.collector.import_sqlite <SQLite 파일>
- 원본 파일에는 sdot_readings(raw, collected_at) 표가 있어야 한다. raw 는 API 한 행의 JSON,
  collected_at 은 받은 시각(ISO 8601)이다.
- 수집기와 같은 규칙(to_record)으로 바꾸고, 이미 있는 (센서, 측정 시각)은 건너뛴다.
  여러 번 실행해도 된다.
"""

import argparse
import json
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collector.models import SdotReading
from app.collector.sdot import to_record
from app.collector.store import collector_engine, insert_new
from app.config import get_settings

# 한 번에 읽어 넣고 커밋하는 행 수
BATCH_ROWS = 10_000


def read_batches(path: Path, size: int) -> Iterator[list[dict[str, Any]]]:
    """원본 파일의 행을 size 개씩 테이블 행으로 바꿔 준다. 깨진 행은 뺀다."""
    # sqlite3 의 with 는 커밋만 하고 닫지 않으므로 closing 으로 닫는다.
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as source:
        cursor = source.execute("SELECT raw, collected_at FROM sdot_readings")
        while chunk := cursor.fetchmany(size):
            records = []
            for raw, collected_at in chunk:
                try:
                    row = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                record = to_record(row, datetime.fromisoformat(collected_at))
                if record is not None:
                    records.append(record)
            yield records


def import_rows(session: Session, path: Path, size: int = BATCH_ROWS) -> int:
    """새로 넣은 행 수. 묶음마다 커밋한다."""
    inserted = 0
    for records in read_batches(path, size):
        inserted += insert_new(session, SdotReading, records)
        session.commit()
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="로컬 SQLite 파일")
    args = parser.parse_args()
    if not args.source.exists():
        print("원본 파일이 없습니다.")
        return 1
    settings = get_settings()
    database_url = settings.collector_database_url.get_secret_value()
    if not database_url:
        print("COLLECTOR_DATABASE_URL 이 비어 있습니다.")
        return 1
    try:
        engine = collector_engine(database_url, settings.collector_connect_timeout_s)
        with Session(engine) as session:
            inserted = import_rows(session, args.source)
    except SQLAlchemyError as error:
        # 예외 문구에 접속 주소가 섞일 수 있어 종류만 남긴다.
        print(f"옮기기 실패 ({type(error).__name__})")
        return 1
    print(f"유동인구: {inserted}행 옮김")
    return 0


if __name__ == "__main__":
    sys.exit(main())
