"""게스트·회원과 토큰, 소셜 계정 연결.

함수는 commit 하지 않는다. 한 요청의 변경을 호출한 쪽에서 한 번에 commit 한다.
"""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, exists, select, update
from sqlalchemy.orm import Session

from app.models import (
    AuthSession,
    RouteHistory,
    SearchHistory,
    SocialAccount,
    User,
    UserProfile,
    utc_now,
)
from core.profiles import DEFAULT_PRESET

TOKEN_BYTES = 32
# 사용자가 지워질 때 함께 지울 테이블
USER_OWNED = (AuthSession, SocialAccount, UserProfile, SearchHistory, RouteHistory)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(session: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    session.add(AuthSession(user_id=user_id, token_hash=hash_token(token)))
    session.flush()
    return token


def create_guest(session: Session) -> tuple[User, str]:
    user = User()
    session.add(user)
    session.flush()
    return user, issue_token(session, user.id)


def find_user_by_token(session: Session, token: str, idle_days: int) -> User | None:
    """토큰의 사용자. idle_days 동안 쓰지 않은 토큰은 만료로 본다."""
    now = utc_now()
    auth = session.scalars(
        select(AuthSession).where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.last_used_at >= now - timedelta(days=idle_days),
        )
    ).one_or_none()
    if auth is None:
        return None
    user = session.get_one(User, auth.user_id)
    auth.last_used_at = now
    user.last_seen_at = now
    return user


def revoke_token(session: Session, token: str) -> None:
    session.execute(
        delete(AuthSession).where(AuthSession.token_hash == hash_token(token))
    )


def is_guest(session: Session, user_id: int) -> bool:
    return not session.scalar(select(exists().where(SocialAccount.user_id == user_id)))


def sign_in_with_social(
    session: Session,
    current_user_id: int | None,
    provider: str,
    provider_user_id: str,
    email: str | None,
) -> tuple[int, str]:
    """소셜 로그인 후 쓸 사용자 id 와 새 토큰.

    - 처음 보는 소셜 계정: 지금 쓰던 사용자(게스트면 회원이 됨)에 연결한다.
    - 이미 연결된 소셜 계정: 그 회원으로 로그인하고, 게스트로 쌓은 이력은 옮긴다.
    """
    account = session.scalars(
        select(SocialAccount).where(
            SocialAccount.provider == provider,
            SocialAccount.provider_user_id == provider_user_id,
        )
    ).one_or_none()
    if account is None:
        if current_user_id is None:
            user = User()
            session.add(user)
            session.flush()
            current_user_id = user.id
        account = SocialAccount(
            user_id=current_user_id,
            provider=provider,
            provider_user_id=provider_user_id,
        )
        session.add(account)
    elif (
        current_user_id is not None
        and current_user_id != account.user_id
        and is_guest(session, current_user_id)
    ):
        merge_guest(session, current_user_id, account.user_id)
    account.email = email
    session.flush()
    return account.user_id, issue_token(session, account.user_id)


def merge_guest(session: Session, guest_id: int, user_id: int) -> None:
    """게스트의 이력을 회원으로 옮기고 게스트를 지운다. 이동 조건은 회원 것이 우선."""
    for model in (SearchHistory, RouteHistory):
        session.execute(
            update(model).where(model.user_id == guest_id).values(user_id=user_id)
        )
    if session.get(UserProfile, user_id) is None:
        session.execute(
            update(UserProfile)
            .where(UserProfile.user_id == guest_id)
            .values(user_id=user_id)
        )
    delete_users(session, [guest_id])


def delete_users(session: Session, user_ids: list[int]) -> None:
    # SQLite 는 기본으로 외래 키 CASCADE 를 하지 않으므로 직접 지운다.
    for model in USER_OWNED:
        session.execute(delete(model).where(model.user_id.in_(user_ids)))
    session.execute(delete(User).where(User.id.in_(user_ids)))
    session.expire_all()


def purge_inactive_guests(session: Session, retention_days: int) -> int:
    """retention_days 동안 접속하지 않은 게스트를 이력과 함께 지운다."""
    guest_ids = list(
        session.scalars(
            select(User.id).where(
                User.last_seen_at < utc_now() - timedelta(days=retention_days),
                ~exists().where(SocialAccount.user_id == User.id),
            )
        )
    )
    if guest_ids:
        delete_users(session, guest_ids)
    return len(guest_ids)


def load_preset(session: Session, user_id: int) -> str:
    profile = session.get(UserProfile, user_id)
    return profile.preset if profile else DEFAULT_PRESET


def save_preset(session: Session, user_id: int, preset: str) -> None:
    profile = session.get(UserProfile, user_id)
    if profile is None:
        session.add(UserProfile(user_id=user_id, preset=preset))
    else:
        profile.preset = preset
    session.flush()
