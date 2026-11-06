"""길 위 문제 제보를 검사하고 저장한다. 승인·취소는 관리자 API가 부른다."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import REPORT_DESCRIPTION_MAX_LENGTH, Report, utc_now
from app.services.photo_storage import PhotoStorage, PhotoStorageError
from core.graph import Graph
from core.road_point import nearby_road_points

REPORT_KINDS = ("curb", "construction", "obstacle", "damage")
CONSTRUCTION = "construction"
PENDING = "pending"
APPROVED = "approved"
# 화면에서는 "취소"라고 부르지만, 저장 값은 프론트 타입(reportApi.ts)에 맞춰 둔다.
REJECTED = "rejected"
# 승인했지만 현장에서 해결되어 더는 반영하지 않는 제보
RESOLVED = "resolved"

# 유형별로 제보가 유효한 기간. 공사는 길게, 치워질 수 있는 장애물은 짧게 둔다.
EXPIRY_DAYS = {"curb": 90, "construction": 7, "obstacle": 1, "damage": 30}

# 확장자는 사진 내용(맨 앞 바이트)으로 정한다. 사용자가 보낸 파일 이름은 쓰지 않는다.
PHOTO_SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
)
PHOTO_MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class ReportFailure(StrEnum):
    UNKNOWN_KIND = "unknown_kind"
    BLOCKED_NOT_CONSTRUCTION = "blocked_not_construction"
    BAD_PHOTO = "bad_photo"
    PHOTO_TOO_LARGE = "photo_too_large"
    DESCRIPTION_TOO_LONG = "description_too_long"
    OFF_NETWORK = "off_network"
    NOT_EDITABLE = "report_not_editable"
    NOT_PENDING = "report_not_pending"
    EXPIRED = "report_expired"
    NOT_APPROVED = "report_not_approved"
    NOT_FOUND = "report_not_found"
    NOT_REVIEWABLE = "report_not_reviewable"
    PHOTO_STORAGE_FAILED = "photo_storage_failed"


class ReportError(Exception):
    def __init__(self, reason: ReportFailure) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ReportInput:
    kind: str
    blocked: bool
    lon: float
    lat: float
    photo: bytes
    description: str = ""


def photo_extension(photo: bytes) -> str | None:
    for signature, extension in PHOTO_SIGNATURES:
        if photo.startswith(signature):
            return extension
    # WebP 는 RIFF....WEBP 모양이다.
    if photo[:4] == b"RIFF" and photo[8:12] == b"WEBP":
        return ".webp"
    return None


def check_kind(kind: str, blocked: bool) -> None:
    if kind not in REPORT_KINDS:
        raise ReportError(ReportFailure.UNKNOWN_KIND)
    if blocked and kind != CONSTRUCTION:
        raise ReportError(ReportFailure.BLOCKED_NOT_CONSTRUCTION)


def clean_description(description: str) -> str:
    description = description.strip()
    if len(description) > REPORT_DESCRIPTION_MAX_LENGTH:
        raise ReportError(ReportFailure.DESCRIPTION_TOO_LONG)
    return description


def create_report(
    session: Session,
    graph: Graph,
    settings: Settings,
    storage: PhotoStorage,
    user_id: int,
    data: ReportInput,
    now: datetime | None = None,
) -> Report:
    """검사를 모두 통과해야 사진을 쓰고 제보를 넣는다. commit 은 부르는 쪽이 한다."""
    check_kind(data.kind, data.blocked)
    if len(data.photo) > settings.report_photo_max_bytes:
        raise ReportError(ReportFailure.PHOTO_TOO_LARGE)
    description = clean_description(data.description)
    extension = photo_extension(data.photo)
    if extension is None:
        raise ReportError(ReportFailure.BAD_PHOTO)
    points = nearby_road_points(
        graph, data.lon, data.lat, settings.report_snap_radius_m
    )
    if not points:
        raise ReportError(ReportFailure.OFF_NETWORK)

    photo_name = f"{secrets.token_hex(16)}{extension}"
    try:
        storage.save(photo_name, data.photo, PHOTO_MEDIA_TYPES[extension])
    except (PhotoStorageError, OSError) as error:
        raise ReportError(ReportFailure.PHOTO_STORAGE_FAILED) from error

    created = now or utc_now()
    report = Report(
        user_id=user_id,
        kind=data.kind,
        blocked=data.blocked,
        status=PENDING,
        photo_name=photo_name,
        description=description or None,
        lon=data.lon,
        lat=data.lat,
        edge_id=points[0].edge.edge_id,
        created_at=created,
        expires_at=created + timedelta(days=EXPIRY_DAYS[data.kind]),
    )
    session.add(report)
    session.flush()
    return report


def update_report(
    report: Report,
    kind: str | None = None,
    blocked: bool | None = None,
    description: str | None = None,
) -> Report:
    """승인 전(pending) 제보의 유형·통행 불가·설명만 바꾼다. None 은 그대로 둔다.

    위치와 사진은 승인 검토의 근거라 바꾸지 않는다. commit 은 부르는 쪽이 한다.
    """
    if report.status != PENDING:
        raise ReportError(ReportFailure.NOT_EDITABLE)
    new_kind = report.kind if kind is None else kind
    new_blocked = report.blocked if blocked is None else blocked
    check_kind(new_kind, new_blocked)
    new_description = (
        report.description if description is None else clean_description(description)
    )

    report.kind = new_kind
    report.blocked = new_blocked
    report.description = new_description or None
    report.expires_at = report.created_at + timedelta(days=EXPIRY_DAYS[new_kind])
    return report


def is_expired(report: Report, now: datetime | None = None) -> bool:
    expires_at = report.expires_at
    # SQLite 는 시간대 없이 돌려주므로 UTC 로 본다.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= (now or utc_now())


def review_report(report: Report, approve: bool, now: datetime | None = None) -> Report:
    """대기(pending) 제보를 승인하거나 취소한다. commit 은 부르는 쪽이 한다.

    만료된 제보는 취소만 할 수 있다. 이미 의미가 없어진 제보를 승인하지 않게 한다.
    """
    if report.status != PENDING:
        raise ReportError(ReportFailure.NOT_PENDING)
    if approve and is_expired(report, now):
        raise ReportError(ReportFailure.EXPIRED)
    report.status = APPROVED if approve else REJECTED
    return report


def resolve_report(report: Report) -> Report:
    """승인한 제보를 해결됨으로 바꾼다. 만료 여부는 따지지 않는다.

    commit 은 부르는 쪽이 한다.
    """
    if report.status != APPROVED:
        raise ReportError(ReportFailure.NOT_APPROVED)
    report.status = RESOLVED
    return report
