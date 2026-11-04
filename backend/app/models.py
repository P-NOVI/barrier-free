from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# 요청 검사(app.schemas)에서도 같은 길이를 쓴다.
QUERY_MAX_LENGTH = 100
NAME_MAX_LENGTH = 200
ADDRESS_MAX_LENGTH = 300
LABEL_MAX_LENGTH = 20


def utc_now() -> datetime:
    return datetime.now(UTC)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utc_now)


def user_id_column(**kwargs) -> Mapped[int]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), **kwargs)


class User(Base):
    """회원과 게스트. 소셜 계정이 연결되지 않은 사용자가 게스트다."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = created_at_column()
    # 오래 접속하지 않은 게스트를 지울 때 기준. 토큰을 확인할 때마다 갱신한다.
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class SocialAccount(Base):
    """카카오·구글 계정. 한 사용자에 둘 다 연결할 수 있다."""

    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = user_id_column(index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_user_id: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = created_at_column()


class AuthSession(Base):
    """게스트·회원이 요청마다 보내는 토큰."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = user_id_column(index=True)
    # DB가 새어도 토큰으로 접속할 수 없도록 원문 대신 SHA-256 해시만 둔다.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = created_at_column()
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class UserProfile(Base):
    """사용자가 고른 이동 조건 프리셋(core.profiles.PRESETS 의 키)."""

    __tablename__ = "profiles"

    user_id: Mapped[int] = user_id_column(primary_key=True)
    preset: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SearchHistory(Base):
    """장소 검색 이력. 검색 결과에서 장소를 고르지 않았으면 장소 칸이 비어 있다."""

    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = user_id_column(index=True)
    query: Mapped[str] = mapped_column(String(QUERY_MAX_LENGTH))
    place_name: Mapped[str | None] = mapped_column(String(NAME_MAX_LENGTH))
    address: Mapped[str | None] = mapped_column(String(ADDRESS_MAX_LENGTH))
    lon: Mapped[float | None]
    lat: Mapped[float | None]
    created_at: Mapped[datetime] = created_at_column()


class RouteHistory(Base):
    """찾았던 경로의 출발지·도착지와 조건."""

    __tablename__ = "route_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = user_id_column(index=True)
    start_name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    start_lon: Mapped[float]
    start_lat: Mapped[float]
    goal_name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    goal_lon: Mapped[float]
    goal_lat: Mapped[float]
    preset: Mapped[str] = mapped_column(String(40))
    distance_m: Mapped[float]
    created_at: Mapped[datetime] = created_at_column()


class SavedRoute(Base):
    """즐겨찾기한 경로(내 경로). 최근 경로와 같은 칸을 둔다."""

    __tablename__ = "saved_routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = user_id_column(index=True)
    start_name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    start_lon: Mapped[float]
    start_lat: Mapped[float]
    goal_name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    goal_lon: Mapped[float]
    goal_lat: Mapped[float]
    preset: Mapped[str] = mapped_column(String(40))
    distance_m: Mapped[float]
    created_at: Mapped[datetime] = created_at_column()


class SavedPlace(Base):
    """즐겨찾기(kind=favorite)와 이름을 붙인 내 장소(kind=mine. 집, 회사 등)."""

    __tablename__ = "saved_places"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = user_id_column(index=True)
    kind: Mapped[str] = mapped_column(String(20))
    # 내 장소의 이름. 즐겨찾기는 None
    label: Mapped[str | None] = mapped_column(String(LABEL_MAX_LENGTH))
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    address: Mapped[str | None] = mapped_column(String(ADDRESS_MAX_LENGTH))
    lon: Mapped[float]
    lat: Mapped[float]
    created_at: Mapped[datetime] = created_at_column()
