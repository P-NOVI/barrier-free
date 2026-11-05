"""내 제보 조회와 삭제. 함수는 commit 하지 않는다."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Report


def list_reports(session: Session, user_id: int) -> list[Report]:
    rows = session.scalars(
        select(Report)
        .where(Report.user_id == user_id)
        .order_by(Report.created_at.desc(), Report.id.desc())
    )
    return list(rows)


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
