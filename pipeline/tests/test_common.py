import io
import json
import urllib.error
from unittest.mock import patch

import pytest

import common

OVERPASS = {
    "url": "http://overpass.test",
    "user_agent": "agent",
    "attempts": 2,
    "retry_wait_s": 0,
}


class Response:
    def __init__(self, body: dict) -> None:
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        pass

    def read(self) -> bytes:
        return self.body


def answer(body: dict, sent: list):
    def urlopen(request, timeout):
        sent.append(request)
        return Response(body)

    return urlopen


def test_fetch_overpass_sends_user_agent() -> None:
    sent: list = []
    with patch.object(
        common.urllib.request, "urlopen", answer({"elements": [1]}, sent)
    ):
        assert common.fetch_overpass(OVERPASS, "q", 5) == {"elements": [1]}

    assert sent[0].full_url == "http://overpass.test"
    assert sent[0].get_header("User-agent") == "agent"


def test_fetch_overpass_rejects_empty_answer() -> None:
    with patch.object(common.urllib.request, "urlopen", answer({"elements": []}, [])):
        with pytest.raises(SystemExit):
            common.fetch_overpass(OVERPASS, "q", 5)


def busy(code: int):
    return urllib.error.HTTPError(
        "http://overpass.test", code, "busy", {}, io.BytesIO()
    )


def test_fetch_overpass_retries_when_busy() -> None:
    replies = iter([busy(502), Response({"elements": [1]})])

    def urlopen(request, timeout):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    with patch.object(common.urllib.request, "urlopen", urlopen):
        assert common.fetch_overpass(OVERPASS, "q", 5) == {"elements": [1]}


def test_fetch_overpass_gives_up_after_attempts_and_on_other_errors() -> None:
    def always(code: int):
        def urlopen(request, timeout):
            raise busy(code)

        return urlopen

    for code in (504, 400):
        with patch.object(common.urllib.request, "urlopen", always(code)):
            with pytest.raises(urllib.error.HTTPError):
                common.fetch_overpass(OVERPASS, "q", 5)
