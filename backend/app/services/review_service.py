"""경로로 지나간 제보 장소의 리뷰를 검사하고 저장한다."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Report, ReportReview, utc_now
from app.services.report_service import (
    APPROVED,
    ReportError,
    ReportFailure,
    is_expired,
)


def save_review(
    session: Session,
    user_id: int,
    report_id: int,
    outcome: str,
    comment: str,
    now: datetime | None = None,
) -> ReportReview:
    """같은 사용자가 같은 제보에 다시 남기면 덮어쓴다. commit 은 부르는 쪽이 한다.

    승인된 제보에만 남길 수 있다. 통행 불가 공사는 경로가 지나지 않으므로 받지 않는다.
    """
    report = session.get(Report, report_id)
    if report is None:
        raise ReportError(ReportFailure.NOT_FOUND)
    if (
        report.status != APPROVED
        or report.blocked
        or is_expired(report, now or utc_now())
    ):
        raise ReportError(ReportFailure.NOT_REVIEWABLE)

    review = session.scalar(
        select(ReportReview).where(
            ReportReview.report_id == report_id, ReportReview.user_id == user_id
        )
    )
    if review is None:
        review = ReportReview(report_id=report_id, user_id=user_id)
        session.add(review)
    review.outcome = outcome
    review.comment = comment.strip()
    session.flush()
    return review
