"""제보 조회와 삭제. 함수는 commit 하지 않는다."""

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Report, utc_now
from app.services.report_service import APPROVED


def list_reports(session: Session, user_id: int) -> list[Report]:
    rows = session.scalars(
        select(Report)
        .where(Report.user_id == user_id)
        .order_by(Report.created_at.desc(), Report.id.desc())
    )
    return list(rows)


def list_reports_by_status(session: Session, report_status: str) -> list[Report]:
    """모든 사용자의 제보. 관리자 검토용이라 오래된 것부터 준다."""
    rows = session.scalars(
        select(Report)
        .where(Report.status == report_status)
        .order_by(Report.created_at, Report.id)
    )
    return list(rows)


def list_reviewable_reports(
    session: Session, edge_ids: frozenset[int], now: datetime
) -> list[Report]:
    """edge_ids 길에 붙은 승인·미만료 제보. 통행 불가 공사는 경로가 피하므로 뺀다."""
    if not edge_ids:
        return []
    rows = session.scalars(
        select(Report)
        .where(
            Report.status == APPROVED,
            Report.blocked.is_(False),
            Report.expires_at > now,
            Report.edge_id.in_(edge_ids),
        )
        .order_by(Report.id)
    )
    return list(rows)


def get_report_any(session: Session, report_id: int) -> Report | None:
    """누구의 제보든 id 로 찾는다. 관리자 전용."""
    return session.get(Report, report_id)


def get_report(session: Session, user_id: int, report_id: int) -> Report | None:
    """다른 사용자의 제보면 None."""
    return session.scalar(
        select(Report).where(Report.id == report_id, Report.user_id == user_id)
    )


def delete_report(session: Session, user_id: int, report_id: int) -> str | None:
    """제보 하나를 지우고 사진 파일 이름을 돌려준다. 없거나 남의 제보면 None."""
    report = get_report(session, user_id, report_id)
    if report is None:
        return None
    photo_name = report.photo_name
    session.delete(report)
    return photo_name


def purge_expired_reports(
    session: Session, retention_days: int, now: datetime | None = None
) -> list[str]:
    """만료 후 retention_days 가 지난 제보를 지우고 사진 파일 이름들을 돌려준다.

    상태(대기·승인·취소)와 상관없이 지운다. 파일은 commit 한 뒤에 지워야 한다.
    """
    cutoff = (now or utc_now()) - timedelta(days=retention_days)
    expired = Report.expires_at < cutoff
    photo_names = list(session.scalars(select(Report.photo_name).where(expired)))
    if photo_names:
        session.execute(delete(Report).where(expired))
    return photo_names
