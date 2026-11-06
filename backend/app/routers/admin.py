"""관리자 전용. 대기 중인 제보를 보고 승인하거나 취소한다."""

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.deps import AdminUserDep, DbSessionDep, SettingsDep
from app.models import Report
from app.repositories import report_repository
from app.routers.reports import FAILURE_MESSAGES, FAILURE_STATUS
from app.schemas import AdminReportListResponse, AdminReportResponse, RouteError
from app.services.report_service import (
    PENDING,
    ReportError,
    resolve_report,
    review_report,
)

router = APIRouter(prefix="/admin", tags=["admin"])

REPORT_STATUSES = ("pending", "approved", "resolved", "rejected")
PHOTO_MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

ADMIN_ERRORS = {
    401: {"model": RouteError, "description": "로그인하지 않음"},
    403: {"model": RouteError, "description": "관리자가 아님"},
}
NOT_FOUND = {404: {"model": RouteError, "description": "없는 제보"}}


def admin_report_response(row: Report) -> AdminReportResponse:
    return AdminReportResponse(
        id=row.id,
        kind=row.kind,
        blocked=row.blocked,
        status=row.status,
        description=row.description,
        lon=row.lon,
        lat=row.lat,
        created_at=row.created_at,
        expires_at=row.expires_at,
        photo_url=f"/api/admin/reports/{row.id}/photo",
    )


def report_or_404(session: DbSessionDep, report_id: int) -> Report:
    report = report_repository.get_report_any(session, report_id)
    if report is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"reason": "report_not_found", "message": "제보가 없습니다."},
        )
    return report


def change_or_error(session: DbSessionDep, change: Callable[[], object]) -> None:
    """상태를 바꾸고 commit 한다. 바꿀 수 없는 제보면 안내 문구와 함께 오류를 낸다."""
    try:
        change()
    except ReportError as error:
        raise HTTPException(
            FAILURE_STATUS[error.reason],
            detail={
                "reason": error.reason.value,
                "message": FAILURE_MESSAGES[error.reason],
            },
        ) from error
    session.commit()


@router.get(
    "/reports",
    response_model=AdminReportListResponse,
    responses={**ADMIN_ERRORS, 422: {"model": RouteError}},
)
def get_reports(
    _admin: AdminUserDep, session: DbSessionDep, report_status: str = PENDING
) -> AdminReportListResponse:
    """상태별 제보. 기본은 검토를 기다리는 제보."""
    if report_status not in REPORT_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "reason": "unknown_status",
                "message": "알 수 없는 제보 상태입니다.",
            },
        )
    rows = report_repository.list_reports_by_status(session, report_status)
    return AdminReportListResponse(reports=[admin_report_response(r) for r in rows])


@router.get(
    "/reports/{report_id}/photo",
    response_class=FileResponse,
    responses={**ADMIN_ERRORS, **NOT_FOUND},
)
def get_report_photo(
    report_id: int,
    _admin: AdminUserDep,
    session: DbSessionDep,
    settings: SettingsDep,
) -> FileResponse:
    report = report_or_404(session, report_id)
    # 파일 이름은 DB 에 저장된 값만 쓴다. 요청으로 받은 경로는 쓰지 않는다.
    path = settings.report_photo_dir / report.photo_name
    media_type = PHOTO_MEDIA_TYPES.get(path.suffix)
    if media_type is None or not path.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"reason": "photo_not_found", "message": "사진이 없습니다."},
        )
    # 사진에 얼굴·번호판이 있을 수 있어 브라우저·중간 서버에 남기지 않는다.
    return FileResponse(
        path, media_type=media_type, headers={"Cache-Control": "private, no-store"}
    )


@router.post(
    "/reports/{report_id}/approve",
    response_model=AdminReportResponse,
    responses={**ADMIN_ERRORS, **NOT_FOUND, 409: {"model": RouteError}},
)
def approve_report(
    report_id: int, _admin: AdminUserDep, session: DbSessionDep
) -> AdminReportResponse:
    report = report_or_404(session, report_id)
    change_or_error(session, lambda: review_report(report, approve=True))
    return admin_report_response(report)


@router.post(
    "/reports/{report_id}/cancel",
    response_model=AdminReportResponse,
    responses={**ADMIN_ERRORS, **NOT_FOUND, 409: {"model": RouteError}},
)
def cancel_report(
    report_id: int, _admin: AdminUserDep, session: DbSessionDep
) -> AdminReportResponse:
    report = report_or_404(session, report_id)
    change_or_error(session, lambda: review_report(report, approve=False))
    return admin_report_response(report)


@router.post(
    "/reports/{report_id}/resolve",
    response_model=AdminReportResponse,
    responses={**ADMIN_ERRORS, **NOT_FOUND, 409: {"model": RouteError}},
)
def resolve_report_route(
    report_id: int, _admin: AdminUserDep, session: DbSessionDep
) -> AdminReportResponse:
    """승인한 제보가 현장에서 해결되어 더는 반영하지 않을 때."""
    report = report_or_404(session, report_id)
    change_or_error(session, lambda: resolve_report(report))
    return admin_report_response(report)
