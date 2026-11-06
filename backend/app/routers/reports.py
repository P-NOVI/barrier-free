"""길 위 문제 제보. 등록한 제보는 관리자가 승인하기 전까지 대기 상태다."""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.deps import DbSessionDep, GraphDep, SettingsDep, UserDep
from app.models import REPORT_DESCRIPTION_MAX_LENGTH
from app.schemas import (
    Latitude,
    Longitude,
    ReportResponse,
    ReviewRequest,
    ReviewResponse,
    RouteError,
)
from app.services.report_service import (
    ReportError,
    ReportFailure,
    ReportInput,
    create_report,
)
from app.services.review_service import save_review

router = APIRouter(tags=["report"])

FAILURE_STATUS = {
    ReportFailure.UNKNOWN_KIND: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ReportFailure.BLOCKED_NOT_CONSTRUCTION: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ReportFailure.BAD_PHOTO: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ReportFailure.PHOTO_TOO_LARGE: status.HTTP_413_CONTENT_TOO_LARGE,
    ReportFailure.DESCRIPTION_TOO_LONG: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ReportFailure.OFF_NETWORK: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ReportFailure.NOT_EDITABLE: status.HTTP_409_CONFLICT,
    ReportFailure.NOT_PENDING: status.HTTP_409_CONFLICT,
    ReportFailure.EXPIRED: status.HTTP_409_CONFLICT,
    ReportFailure.NOT_APPROVED: status.HTTP_409_CONFLICT,
    ReportFailure.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ReportFailure.NOT_REVIEWABLE: status.HTTP_409_CONFLICT,
}

FAILURE_MESSAGES = {
    ReportFailure.UNKNOWN_KIND: "알 수 없는 제보 유형입니다.",
    ReportFailure.BLOCKED_NOT_CONSTRUCTION: "통행 불가는 공사 제보만 고를 수 있습니다.",
    ReportFailure.BAD_PHOTO: "JPEG, PNG, WebP 사진만 올릴 수 있습니다.",
    ReportFailure.PHOTO_TOO_LARGE: "사진이 너무 큽니다.",
    ReportFailure.DESCRIPTION_TOO_LONG: (
        f"설명은 {REPORT_DESCRIPTION_MAX_LENGTH}자 이하로 적어 주세요."
    ),
    ReportFailure.OFF_NETWORK: "제보 위치 근처에 보행 도로가 없습니다.",
    ReportFailure.NOT_EDITABLE: "검토가 끝난 제보는 고칠 수 없습니다.",
    ReportFailure.NOT_PENDING: "이미 검토가 끝난 제보입니다.",
    ReportFailure.EXPIRED: "만료된 제보는 승인할 수 없습니다. 취소만 할 수 있어요.",
    ReportFailure.NOT_APPROVED: "승인된 제보만 해결됨으로 바꿀 수 있습니다.",
    ReportFailure.NOT_FOUND: "제보를 찾을 수 없습니다.",
    ReportFailure.NOT_REVIEWABLE: "리뷰를 받지 않는 제보입니다.",
}


@router.post(
    "/reports",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        413: {"model": RouteError},
        422: {"model": RouteError},
    },
)
def post_report(
    user: UserDep,
    session: DbSessionDep,
    graph: GraphDep,
    settings: SettingsDep,
    kind: Annotated[str, Form()],
    lon: Annotated[Longitude, Form()],
    lat: Annotated[Latitude, Form()],
    photo: Annotated[UploadFile, File(description="JPEG, PNG, WebP")],
    blocked: Annotated[bool, Form()] = False,
    description: Annotated[str, Form()] = "",
) -> ReportResponse:
    # 한도보다 한 바이트만 더 읽어, 큰 파일 전체를 메모리에 올리지 않고 거른다.
    content = photo.file.read(settings.report_photo_max_bytes + 1)
    try:
        report = create_report(
            session,
            graph,
            settings,
            user.id,
            ReportInput(kind, blocked, lon, lat, content, description),
        )
    except ReportError as error:
        raise HTTPException(
            FAILURE_STATUS[error.reason],
            detail={
                "reason": error.reason,
                "message": FAILURE_MESSAGES[error.reason],
            },
        ) from error
    session.commit()
    return ReportResponse.model_validate(report, from_attributes=True)


@router.post(
    "/reports/{report_id}/review",
    response_model=ReviewResponse,
    responses={404: {"model": RouteError}, 409: {"model": RouteError}},
)
def post_review(
    report_id: int,
    request: ReviewRequest,
    user: UserDep,
    session: DbSessionDep,
) -> ReviewResponse:
    try:
        review = save_review(
            session, user.id, report_id, request.outcome, request.comment
        )
    except ReportError as error:
        raise HTTPException(
            FAILURE_STATUS[error.reason],
            detail={
                "reason": error.reason,
                "message": FAILURE_MESSAGES[error.reason],
            },
        ) from error
    session.commit()
    return ReviewResponse.model_validate(review, from_attributes=True)
