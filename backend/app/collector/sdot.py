"""S-DoT 유동인구를 sdot_readings 에 쌓는다.

API 는 최신순으로 과거 행을 길게 준다.
(1000행 ≈ 1.5시간, 쪽을 이어 받으면 최소 11일 전까지)
DB의 최신 측정 시각보다 collector_sdot_overlap_minutes 앞까지 최신 쪽부터 거슬러 받고,
이미 있는 (센서, 측정 시각)은 건너뛴다. 실행이 며칠 빠져도 다음 실행이 메운다.
모든 쪽을 받은 뒤 한 번에 넣으므로, 중간에 실패하면 아무것도 넣지 않고 다음 실행이
같은 지점부터 다시 받는다.
"""

from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collector.models import SdotReading
from app.collector.store import as_kst, insert_new
from app.config import Settings
from app.services.congestion_service import (
    KST,
    SENSING_TIME_FORMAT,
    CongestionError,
    request_rows,
)


class PageLimitError(CongestionError):
    """collector_sdot_max_pages 쪽을 받아도 이어 받을 지점에 닿지 못했을 때."""


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


def fetch_since(
    client: httpx.Client, until: datetime, page_size: int, max_pages: int
) -> tuple[list[dict[str, Any]], bool]:
    """최신 쪽부터 until 보다 이른 측정이 나올 때까지 받는다.

    반환: (행, API 가 until 앞에서 끝났는지). 끝났으면 그 사이는 다시 받을 수 없다.
    PageLimitError: max_pages 쪽 안에 until 에 닿지 못했을 때
    """
    rows: list[dict[str, Any]] = []
    for page in range(max_pages):
        page_rows = request_rows(client, page_size, page * page_size + 1)
        rows += page_rows
        times = [
            record["measured_at"]
            for row in page_rows
            if (record := to_record(row, until)) is not None
        ]
        if times and min(times) < until:
            return rows, False
        if len(page_rows) < page_size:
            return rows, True
    raise PageLimitError(f"{max_pages}쪽")


def resume_point(session: Session, overlap: timedelta) -> datetime | None:
    """이번에 어디까지 거슬러 받을지. DB가 비었으면 None."""
    latest = session.scalar(select(func.max(SdotReading.measured_at)))
    return None if latest is None else as_kst(latest) - overlap


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


def unique_records(
    rows: list[dict[str, Any]], collected: datetime
) -> list[dict[str, Any]]:
    """깨진 행을 빼고 (센서, 측정 시각)마다 한 행만 남긴다."""
    # 쪽을 나눠 받는 사이 새 행이 앞에 붙으면 같은 행이 두 번 올 수 있다.
    records = {
        (record["sensor_code"], record["measured_at"]): record
        for row in rows
        if (record := to_record(row, collected)) is not None
    }
    return list(records.values())


def collect_sdot(
    session: Session, client: httpx.Client, settings: Settings, now: datetime
) -> int:
    """새로 넣은 행 수. CongestionError: API 호출·응답 실패, 쪽 수 한도"""
    until = resume_point(
        session, timedelta(minutes=settings.collector_sdot_overlap_minutes)
    )
    if until is None:
        rows = fetch_rows(client, settings.collector_sdot_rows, settings.sdot_page_size)
    else:
        rows, exhausted = fetch_since(
            client, until, settings.sdot_page_size, settings.collector_sdot_max_pages
        )
        if exhausted:
            print(
                f"유동인구: 경고 - API 가 {until.isoformat()} 까지 주지 않아 "
                "그 사이에 빈 구간이 생겼습니다"
            )
    return insert_new(session, SdotReading, unique_records(rows, now))
