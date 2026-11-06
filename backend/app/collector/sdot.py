"""S-DoT 유동인구를 sdot_readings 에 쌓는다.

API 는 최신순으로 과거 행을 길게 준다(1000행 ≈ 2시간). 최신 collector_sdot_rows 행을
받아 이미 있는 (센서, 측정 시각)은 건너뛰므로, 실행이 몇 번 빠져도 다음 실행이 메운다.
"""

from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.collector.models import SdotReading
from app.collector.store import insert_new
from app.config import Settings
from app.services.congestion_service import KST, SENSING_TIME_FORMAT, request_rows


def fetch_rows(
    client: httpx.Client, total: int, page_size: int
) -> list[dict[str, Any]]:
    """최신 total 행. 마지막 쪽이 덜 차면 거기서 멈춘다."""
    rows: list[dict[str, Any]] = []
    for start in range(1, total + 1, page_size):
        page = request_rows(client, min(page_size, total - start + 1), start)
        rows += page
        if len(page) < page_size:
            break
    return rows


def to_record(row: dict[str, Any], collected: datetime) -> dict[str, Any] | None:
    """API 한 행을 테이블 행으로. 코드·시각·방문자 수가 깨진 행은 None."""
    try:
        return {
            "sensor_code": int(row["SERIAL"]),
            "measured_at": datetime.strptime(
                row["SENSING_TIME"], SENSING_TIME_FORMAT
            ).replace(tzinfo=KST),
            "visitor_count": int(row["VISITOR_COUNT"]),
            "region": row.get("REGION") or None,
            "district": row.get("AUTONOMOUS_DISTRICT") or None,
            "dong": row.get("ADMINISTRATIVE_DISTRICT") or None,
            "collected_at": collected,
        }
    except (KeyError, ValueError, TypeError):
        return None


def collect_sdot(
    session: Session, client: httpx.Client, settings: Settings, now: datetime
) -> int:
    """새로 넣은 행 수. CongestionError: API 호출·응답 실패"""
    rows = fetch_rows(client, settings.collector_sdot_rows, settings.sdot_page_size)
    # 쪽을 나눠 받는 사이 새 행이 앞에 붙으면 같은 행이 두 번 올 수 있다.
    records = {
        (record["sensor_code"], record["measured_at"]): record
        for row in rows
        if (record := to_record(row, now)) is not None
    }
    return insert_new(session, SdotReading, list(records.values()))
