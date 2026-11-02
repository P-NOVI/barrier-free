from collections.abc import Callable, Iterator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.deps import get_db_session, get_oauth_client
from app.main import app
from app.models import SocialAccount
from app.services.oauth_service import create_oauth_client

Handler = Callable[[httpx.Request], httpx.Response]

SETTINGS = Settings(
    _env_file=None,
    kakao_rest_api_key="kakao-id",
    kakao_client_secret="kakao-secret",
    google_client_id="google-id",
    google_client_secret="google-secret",
)
FRONTEND = SETTINGS.frontend_url
KAKAO_USER = {
    "id": 1234,
    "kakao_account": {
        "email": "a@example.com",
        "is_email_valid": True,
        "is_email_verified": True,
    },
}


def social_api(user: dict, token_status: int = 200) -> Handler:
    """토큰 교환과 사용자 정보 요청에 답하는 카카오·구글 대신."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = {"access_token": "access"} if token_status == 200 else {}
            return httpx.Response(token_status, json=body)
        return httpx.Response(200, json=user)

    return handle


@pytest.fixture
def received(db_session: Session) -> Iterator[Callable[[Handler], list]]:
    """카카오·구글 API 대신 handler 가 답하게 하고, 받은 요청 목록을 돌려준다."""
    requests: list[httpx.Request] = []

    def use(handler: Handler) -> list[httpx.Request]:
        def record(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        def override() -> Iterator[httpx.Client]:
            with create_oauth_client(SETTINGS, httpx.MockTransport(record)) as mock:
                yield mock

        app.dependency_overrides[get_oauth_client] = override
        return requests

    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    use(social_api(KAKAO_USER))
    yield use
    app.dependency_overrides.clear()


@pytest.fixture
def client(received) -> TestClient:
    return TestClient(app, follow_redirects=False)


def start_login(client: TestClient, provider: str = "kakao") -> str:
    """로그인을 시작하고 카카오·구글로 넘긴 state 를 돌려준다."""
    response = client.get(f"/api/auth/{provider}/login")
    return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]


def finish_login(client: TestClient, provider: str = "kakao") -> httpx.Response:
    state = start_login(client, provider)
    return client.get(
        f"/api/auth/{provider}/callback", params={"code": "the-code", "state": state}
    )


def test_login_redirects_to_kakao(client: TestClient) -> None:
    response = client.get("/api/auth/kakao/login")

    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        "https://kauth.kakao.com/oauth/authorize"
    )
    query = parse_qs(location.query)
    assert query["client_id"] == ["kakao-id"]
    assert query["redirect_uri"] == ["http://localhost:8000/api/auth/kakao/callback"]
    assert query["response_type"] == ["code"]
    assert "scope" not in query
    set_cookie = response.headers["set-cookie"].lower()
    assert set_cookie.startswith(f"{SETTINGS.oauth_state_cookie_name}=")
    assert "httponly" in set_cookie


def test_google_login_asks_for_email(client: TestClient) -> None:
    response = client.get("/api/auth/google/login")

    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["scope"] == ["openid email"]
    assert query["redirect_uri"] == ["http://localhost:8000/api/auth/google/callback"]


def test_login_without_keys_is_503(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)

    response = client.get("/api/auth/google/login")

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "login_unavailable"


def test_unknown_provider_is_422(client: TestClient) -> None:
    assert client.get("/api/auth/naver/login").status_code == 422


def test_callback_signs_in_and_keeps_guest_history(
    client: TestClient, received, db_session: Session
) -> None:
    client.post("/api/me/searches", json={"query": "서울역"})
    guest_token = client.cookies[SETTINGS.auth_cookie_name]
    requests = received(social_api(KAKAO_USER))

    response = finish_login(client)

    assert response.status_code == 303
    assert response.headers["location"] == FRONTEND
    assert response.cookies[SETTINGS.auth_cookie_name] != guest_token
    token_request = parse_qs(requests[0].content.decode())
    assert token_request["code"] == ["the-code"]
    assert token_request["client_secret"] == ["kakao-secret"]
    assert token_request["redirect_uri"] == [
        "http://localhost:8000/api/auth/kakao/callback"
    ]
    assert requests[1].headers["authorization"] == "Bearer access"
    session = client.get("/api/session").json()
    assert session["is_guest"] is False
    assert session["providers"] == ["kakao"]
    searches = client.get("/api/me/searches").json()["searches"]
    assert [s["query"] for s in searches] == ["서울역"]
    account = db_session.scalars(select(SocialAccount)).one()
    assert (account.provider_user_id, account.email) == ("1234", "a@example.com")


def test_guest_on_other_device_joins_existing_member(
    received, db_session: Session
) -> None:
    phone = TestClient(app, follow_redirects=False)
    laptop = TestClient(app, follow_redirects=False)
    finish_login(phone)
    phone.post("/api/me/searches", json={"query": "시청"})
    laptop.post("/api/me/searches", json={"query": "서울역"})

    finish_login(laptop)

    queries = {s["query"] for s in phone.get("/api/me/searches").json()["searches"]}
    assert queries == {"시청", "서울역"}
    assert len(db_session.scalars(select(SocialAccount)).all()) == 1


def test_wrong_state_fails_without_calling_kakao(client: TestClient, received) -> None:
    requests = received(social_api(KAKAO_USER))
    start_login(client)

    response = client.get(
        "/api/auth/kakao/callback", params={"code": "the-code", "state": "forged"}
    )

    assert response.headers["location"] == f"{FRONTEND}/?login=failed"
    assert requests == []


def test_callback_without_state_cookie_fails(client: TestClient) -> None:
    response = client.get(
        "/api/auth/kakao/callback", params={"code": "the-code", "state": "any"}
    )

    assert response.headers["location"] == f"{FRONTEND}/?login=failed"


def test_cancelled_login_fails(client: TestClient) -> None:
    state = start_login(client)

    response = client.get(
        "/api/auth/kakao/callback",
        params={"error": "access_denied", "state": state},
    )

    assert response.headers["location"] == f"{FRONTEND}/?login=failed"


def test_state_from_other_provider_fails(client: TestClient) -> None:
    state = start_login(client, "google")

    response = client.get(
        "/api/auth/kakao/callback", params={"code": "the-code", "state": state}
    )

    assert response.headers["location"] == f"{FRONTEND}/?login=failed"


def test_rejected_code_fails(client: TestClient, received) -> None:
    received(social_api(KAKAO_USER, token_status=401))

    response = finish_login(client)

    assert response.headers["location"] == f"{FRONTEND}/?login=failed"
    assert client.get("/api/session").json()["is_guest"] is True


def test_kakao_timeout_fails(client: TestClient, received) -> None:
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("시간 초과", request=request)

    received(time_out)

    assert finish_login(client).headers["location"] == f"{FRONTEND}/?login=failed"


def test_google_unverified_email_is_not_saved(
    client: TestClient, received, db_session: Session
) -> None:
    received(social_api({"sub": "g-1", "email": "b@example.com"}))

    finish_login(client, "google")

    account = db_session.scalars(select(SocialAccount)).one()
    assert (account.provider, account.provider_user_id) == ("google", "g-1")
    assert account.email is None


def test_logout_forgets_user(client: TestClient) -> None:
    finish_login(client)
    token = client.cookies[SETTINGS.auth_cookie_name]

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert SETTINGS.auth_cookie_name not in client.cookies
    # 지운 토큰을 다시 보내도 로그인 상태가 아니다.
    reused = TestClient(app, cookies={SETTINGS.auth_cookie_name: token})
    assert reused.get("/api/session").json()["is_guest"] is True
