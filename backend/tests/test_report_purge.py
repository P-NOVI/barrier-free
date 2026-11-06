from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Report, utc_now
from app.repositories.report_repository import purge_expired_reports

RETENTION_DAYS = 30


def add_report(
    session: Session, photo_name: str, expired_days_ago: float, status: str
) -> None:
    now = utc_now()
    session.add(
        Report(
            kind="curb",
            blocked=False,
            status=status,
            photo_name=photo_name,
            lon=126.9779,
            lat=37.5663,
            edge_id=1,
            created_at=now - timedelta(days=120),
            expires_at=now - timedelta(days=expired_days_ago),
        )
    )


def test_purges_only_reports_expired_longer_than_retention(
    db_session: Session,
) -> None:
    add_report(db_session, "old.jpg", RETENTION_DAYS + 1, "pending")
    add_report(db_session, "recent.jpg", RETENTION_DAYS - 1, "approved")
    add_report(db_session, "alive.jpg", -5, "pending")
    db_session.flush()

    removed = purge_expired_reports(db_session, RETENTION_DAYS)
    db_session.commit()

    assert removed == ["old.jpg"]
    kept = db_session.scalars(select(Report.photo_name).order_by(Report.id))
    assert list(kept) == ["recent.jpg", "alive.jpg"]


def test_purges_every_status_once_past_retention(db_session: Session) -> None:
    for status in ("pending", "approved", "rejected"):
        add_report(db_session, f"{status}.jpg", RETENTION_DAYS + 10, status)
    db_session.flush()

    removed = purge_expired_reports(db_session, RETENTION_DAYS)
    db_session.commit()

    assert sorted(removed) == ["approved.jpg", "pending.jpg", "rejected.jpg"]
    assert list(db_session.scalars(select(Report))) == []


def test_nothing_to_purge(db_session: Session) -> None:
    add_report(db_session, "alive.jpg", -5, "pending")
    db_session.flush()

    assert purge_expired_reports(db_session, RETENTION_DAYS) == []
    assert len(list(db_session.scalars(select(Report)))) == 1
