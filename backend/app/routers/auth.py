"""카카오·구글 로그인과 로그아웃.

화면은 /api/auth/{provider}/login 으로 이동만 한다. 로그인을 마치면 콜백이
토큰 쿠키를 주고 화면(frontend_url)으로 돌려보낸다. 실패하면 ?login=failed 를 붙인다.
"""

import secrets

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.deps import DbSessionDep, OAuthClientDep, SettingsDep, set_token_cookie
from app.repositories.user_repository import (
    find_user_by_token,
    revoke_token,
    sign_in_with_social,
)
from app.schemas import RouteError
from app.services.oauth_service import (
    OAuthError,
    Provider,
    authorize_url,
    fetch_profile,
    oauth_app,
    redirect_uri,
)

router = APIRouter(prefix="/auth", tags=["auth"])

STATE_BYTES = 32


def back_to_frontend(settings: Settings, failed: bool = False) -> RedirectResponse:
    url = f"{settings.frontend_url}/?login=failed" if failed else settings.frontend_url
    response = RedirectResponse(url, status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.oauth_state_cookie_name)
    return response


@router.get(
    "/{provider}/login",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    responses={503: {"model": RouteError}},
)
def login(provider: Provider, settings: SettingsDep) -> RedirectResponse:
    """카카오·구글 로그인 화면으로 보낸다."""
    app = oauth_app(settings, provider)
    if app is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": "login_unavailable",
                "message": f"{provider} 로그인 키가 없습니다. "
                "backend/.env 를 확인하세요.",
            },
        )
    state = secrets.token_urlsafe(STATE_BYTES)
    response = RedirectResponse(
        authorize_url(app, redirect_uri(settings, provider), state),
        status.HTTP_303_SEE_OTHER,
    )
    # 돌아온 state 가 이 값과 같아야 이 브라우저에서 시작한 로그인으로 본다.
    response.set_cookie(
        settings.oauth_state_cookie_name,
        f"{provider}:{state}",
        max_age=settings.oauth_state_ttl_s,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    return response


@router.get(
    "/{provider}/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
)
def callback(
    provider: Provider,
    request: Request,
    session: DbSessionDep,
    settings: SettingsDep,
    client: OAuthClientDep,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    """로그인을 마치고 돌아온 곳. 게스트로 쌓은 이력은 로그인한 계정으로 옮긴다."""
    app = oauth_app(settings, provider)
    expected = request.cookies.get(settings.oauth_state_cookie_name, "")
    # 사용자가 동의를 취소하면 code 없이 error 만 온다.
    if (
        app is None
        or not code
        or not state
        or not secrets.compare_digest(expected, f"{provider}:{state}")
    ):
        return back_to_frontend(settings, failed=True)
    try:
        profile = fetch_profile(
            client, provider, app, redirect_uri(settings, provider), code
        )
    except OAuthError:
        return back_to_frontend(settings, failed=True)

    old_token = request.cookies.get(settings.auth_cookie_name)
    current = (
        find_user_by_token(session, old_token, settings.token_idle_days)
        if old_token
        else None
    )
    _, token = sign_in_with_social(
        session,
        current.id if current else None,
        provider,
        profile.provider_user_id,
        profile.email,
    )
    if old_token:
        revoke_token(session, old_token)
    session.commit()
    response = back_to_frontend(settings)
    set_token_cookie(response, settings, token)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request, response: Response, session: DbSessionDep, settings: SettingsDep
) -> None:
    """토큰을 지운다. 이후 이력을 저장하면 새 게스트가 된다."""
    token = request.cookies.get(settings.auth_cookie_name)
    if token:
        revoke_token(session, token)
        session.commit()
    response.delete_cookie(
        settings.auth_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
