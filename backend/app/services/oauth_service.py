"""카카오·구글 로그인(OAuth 인가 코드 방식).

1. 로그인 화면 주소로 보낸다(authorize_url).
2. 사용자가 동의하면 콜백 주소로 code 가 온다.
3. code 를 토큰으로 바꾸고, 토큰으로 사용자 id 를 받는다(fetch_profile).

code·토큰·키는 로그나 응답에 내보내지 않는다.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings


class Provider(StrEnum):
    KAKAO = "kakao"
    GOOGLE = "google"


class OAuthError(Exception):
    """카카오·구글과 주고받다 실패했다. 이유는 사용자에게 보이지 않는다."""


@dataclass(frozen=True)
class OAuthApp:
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    user_url: str
    # None 이면 콘솔에서 정한 동의 항목을 쓴다(카카오).
    scope: str | None


@dataclass(frozen=True)
class SocialProfile:
    provider_user_id: str
    email: str | None


def oauth_app(settings: Settings, provider: Provider) -> OAuthApp | None:
    """키가 없으면 None."""
    if provider is Provider.KAKAO:
        app = OAuthApp(
            client_id=settings.kakao_rest_api_key.get_secret_value(),
            client_secret=settings.kakao_client_secret.get_secret_value(),
            authorize_url=f"{settings.kakao_auth_base_url}/oauth/authorize",
            token_url=f"{settings.kakao_auth_base_url}/oauth/token",
            user_url=settings.kakao_user_url,
            scope=None,
        )
    else:
        app = OAuthApp(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret.get_secret_value(),
            authorize_url=settings.google_authorize_url,
            token_url=settings.google_token_url,
            user_url=settings.google_user_url,
            scope="openid email",
        )
    return app if app.client_id and app.client_secret else None


def redirect_uri(settings: Settings, provider: Provider) -> str:
    return f"{settings.oauth_redirect_base_url}/api/auth/{provider}/callback"


def authorize_url(app: OAuthApp, redirect: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": app.client_id,
        "redirect_uri": redirect,
        "state": state,
    }
    if app.scope:
        params["scope"] = app.scope
    return f"{app.authorize_url}?{urlencode(params)}"


def create_oauth_client(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    return httpx.Client(timeout=settings.oauth_timeout_s, transport=transport)


def fetch_profile(
    client: httpx.Client,
    provider: Provider,
    app: OAuthApp,
    redirect: str,
    code: str,
) -> SocialProfile:
    token = _request_json(
        client,
        "POST",
        app.token_url,
        data={
            "grant_type": "authorization_code",
            "client_id": app.client_id,
            "client_secret": app.client_secret,
            "redirect_uri": redirect,
            "code": code,
        },
    )
    access_token = token.get("access_token")
    if not isinstance(access_token, str):
        raise OAuthError("토큰 응답에 access_token 이 없습니다.")
    user = _request_json(
        client,
        "GET",
        app.user_url,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if provider is Provider.KAKAO:
        return _kakao_profile(user)
    return _google_profile(user)


def _request_json(
    client: httpx.Client, method: str, url: str, **kwargs: Any
) -> dict[str, Any]:
    try:
        response = client.request(method, url, **kwargs)
    except httpx.HTTPError as error:
        raise OAuthError("로그인 서버에 연결하지 못했습니다.") from error
    if response.status_code != httpx.codes.OK:
        raise OAuthError(f"로그인 서버 응답 HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError as error:
        raise OAuthError("로그인 서버 응답이 JSON 이 아닙니다.") from error
    if not isinstance(body, dict):
        raise OAuthError("로그인 서버 응답 형식이 다릅니다.")
    return body


def _kakao_profile(user: dict[str, Any]) -> SocialProfile:
    user_id = user.get("id")
    if not isinstance(user_id, int):
        raise OAuthError("카카오 사용자 id 가 없습니다.")
    account = user.get("kakao_account")
    account = account if isinstance(account, dict) else {}
    # 확인된 이메일만 저장한다. 동의하지 않았으면 없다.
    verified = account.get("is_email_valid") and account.get("is_email_verified")
    email = account.get("email") if verified else None
    return SocialProfile(str(user_id), email if isinstance(email, str) else None)


def _google_profile(user: dict[str, Any]) -> SocialProfile:
    user_id = user.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise OAuthError("구글 사용자 id(sub) 가 없습니다.")
    email = user.get("email") if user.get("email_verified") is True else None
    return SocialProfile(user_id, email if isinstance(email, str) else None)
