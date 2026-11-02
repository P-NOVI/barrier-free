from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuthSession, SearchHistory, User, utc_now
from app.repositories.history_repository import add_search, list_searches
from app.repositories.user_repository import (
    create_guest,
    find_user_by_token,
    is_guest,
    load_preset,
    purge_inactive_guests,
    revoke_token,
    save_preset,
    sign_in_with_social,
)
from core.profiles import DEFAULT_PRESET

IDLE_DAYS = 30
KEEP = 50


def count(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_guest_token_finds_guest(db_session: Session) -> None:
    guest, token = create_guest(db_session)

    assert find_user_by_token(db_session, token, IDLE_DAYS).id == guest.id
    assert is_guest(db_session, guest.id)


def test_token_is_stored_as_hash(db_session: Session) -> None:
    _, token = create_guest(db_session)

    stored = db_session.scalars(select(AuthSession.token_hash)).one()
    assert stored != token
    assert len(stored) == 64


def test_unknown_token_finds_nobody(db_session: Session) -> None:
    create_guest(db_session)

    assert find_user_by_token(db_session, "wrong", IDLE_DAYS) is None


def test_idle_token_expires(db_session: Session) -> None:
    _, token = create_guest(db_session)
    auth = db_session.scalars(select(AuthSession)).one()
    auth.last_used_at = utc_now() - timedelta(days=IDLE_DAYS + 1)
    db_session.flush()

    assert find_user_by_token(db_session, token, IDLE_DAYS) is None


def test_revoked_token_finds_nobody(db_session: Session) -> None:
    _, token = create_guest(db_session)

    revoke_token(db_session, token)

    assert find_user_by_token(db_session, token, IDLE_DAYS) is None


def test_new_social_account_turns_guest_into_member(db_session: Session) -> None:
    guest, _ = create_guest(db_session)
    add_search(db_session, guest.id, KEEP, "서울역")

    user_id, token = sign_in_with_social(
        db_session, guest.id, "kakao", "k1", "a@example.com"
    )

    assert user_id == guest.id
    assert not is_guest(db_session, user_id)
    assert find_user_by_token(db_session, token, IDLE_DAYS).id == user_id
    assert [row.query for row in list_searches(db_session, user_id, KEEP)] == ["서울역"]


def test_sign_in_without_guest_creates_member(db_session: Session) -> None:
    user_id, _ = sign_in_with_social(db_session, None, "google", "g1", None)

    assert not is_guest(db_session, user_id)


def test_existing_member_takes_over_guest_history(db_session: Session) -> None:
    member_id, _ = sign_in_with_social(db_session, None, "kakao", "k1", None)
    add_search(db_session, member_id, KEEP, "시청")
    save_preset(db_session, member_id, "stroller")
    guest, _ = create_guest(db_session)
    add_search(db_session, guest.id, KEEP, "서울역")
    save_preset(db_session, guest.id, "elderly")

    user_id, _ = sign_in_with_social(db_session, guest.id, "kakao", "k1", None)

    assert user_id == member_id
    queries = {row.query for row in list_searches(db_session, member_id, KEEP)}
    assert queries == {"시청", "서울역"}
    # 이동 조건은 회원이 저장해 둔 것을 쓴다.
    assert load_preset(db_session, member_id) == "stroller"
    assert db_session.get(User, guest.id) is None


def test_member_without_preset_takes_guest_preset(db_session: Session) -> None:
    member_id, _ = sign_in_with_social(db_session, None, "kakao", "k1", None)
    guest, _ = create_guest(db_session)
    save_preset(db_session, guest.id, "elderly")

    sign_in_with_social(db_session, guest.id, "kakao", "k1", None)

    assert load_preset(db_session, member_id) == "elderly"


def test_member_can_link_second_provider(db_session: Session) -> None:
    member_id, _ = sign_in_with_social(db_session, None, "kakao", "k1", None)

    user_id, _ = sign_in_with_social(db_session, member_id, "google", "g1", None)

    assert user_id == member_id


def test_member_signing_into_other_member_keeps_both(db_session: Session) -> None:
    first_id, _ = sign_in_with_social(db_session, None, "kakao", "k1", None)
    second_id, _ = sign_in_with_social(db_session, None, "kakao", "k2", None)
    add_search(db_session, first_id, KEEP, "시청")

    user_id, _ = sign_in_with_social(db_session, first_id, "kakao", "k2", None)

    assert user_id == second_id
    assert len(list_searches(db_session, first_id, KEEP)) == 1


def test_purge_removes_only_inactive_guests(db_session: Session) -> None:
    old_guest, _ = create_guest(db_session)
    add_search(db_session, old_guest.id, KEEP, "서울역")
    recent_guest, _ = create_guest(db_session)
    member_id, _ = sign_in_with_social(db_session, None, "kakao", "k1", None)
    long_ago = utc_now() - timedelta(days=31)
    old_guest.last_seen_at = long_ago
    db_session.get_one(User, member_id).last_seen_at = long_ago
    db_session.flush()

    assert purge_inactive_guests(db_session, 30) == 1

    remaining = set(db_session.scalars(select(User.id)))
    assert remaining == {recent_guest.id, member_id}
    assert count(db_session, SearchHistory) == 0


def test_default_preset_when_not_saved(db_session: Session) -> None:
    guest, _ = create_guest(db_session)

    assert load_preset(db_session, guest.id) == DEFAULT_PRESET


def test_save_preset_overwrites(db_session: Session) -> None:
    guest, _ = create_guest(db_session)

    save_preset(db_session, guest.id, "elderly")
    save_preset(db_session, guest.id, "crutches")

    assert load_preset(db_session, guest.id) == "crutches"
