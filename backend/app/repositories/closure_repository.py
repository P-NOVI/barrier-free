"""경로 탐색에서 뺄 길. 관리자가 승인한 통행 불가 제보가 붙은 길이다."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Report

# 관리자가 승인한 제보의 상태 값. 프론트 ReportStatus(reportApi.ts)와 같다.
APPROVED = "approved"


def closed_edge_ids(session: Session, now: datetime) -> frozenset[int]:
    """승인됐고 아직 만료되지 않은 통행 불가 제보의 길(core.graph.Arc.edge_id)."""
    rows = session.scalars(
        select(Report.edge_id).where(
            Report.status == APPROVED,
            Report.blocked.is_(True),
            Report.expires_at > now,
        )
    )
    return frozenset(rows)
