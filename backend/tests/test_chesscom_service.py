import asyncio

import httpx
import pytest

from app.services import chesscom


class DummyClient:
    def __init__(self, response: httpx.Response):
        self.response = response
        self.last_url = ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str) -> httpx.Response:
        self.last_url = url
        return self.response


def _response(status: int, url: str, text: str = "", json_data: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", url)
    if json_data is not None:
        return httpx.Response(status, request=request, json=json_data)
    return httpx.Response(status, request=request, text=text)


def test_normalize_username_from_plain_value():
    assert chesscom.normalize_username(" Hikaru ") == "hikaru"


def test_normalize_username_from_profile_url():
    assert chesscom.normalize_username("https://www.chess.com/member/Hikaru") == "hikaru"


def test_normalize_username_from_at_prefixed_handle():
    assert chesscom.normalize_username("@Hikaru") == "hikaru"


def test_fetch_archives_uses_normalized_username(monkeypatch):
    url = "https://api.chess.com/pub/player/hikaru/games/archives"
    response = _response(
        200,
        url,
        json_data={
            "archives": [
                "https://api.chess.com/pub/player/hikaru/games/2026/02",
                "https://api.chess.com/pub/player/hikaru/games/2026/01",
            ]
        },
    )
    dummy = DummyClient(response)
    monkeypatch.setattr(chesscom, "build_client", lambda: dummy)

    archives = asyncio.run(chesscom.fetch_archives(" https://www.chess.com/member/Hikaru "))
    assert len(archives) == 2
    assert dummy.last_url.endswith("/hikaru/games/archives")


def test_fetch_archives_reports_web_filter_block(monkeypatch):
    url = "https://api.chess.com/pub/player/hikaru/games/archives"
    response = _response(403, url, text="<html><title>TR - Web Filter Violation</title></html>")
    monkeypatch.setenv("HTTP_PROXY", "")
    monkeypatch.setenv("HTTPS_PROXY", "")
    monkeypatch.setattr(chesscom, "build_client", lambda: DummyClient(response))

    with pytest.raises(ValueError, match="Blocked by network web filter"):
        asyncio.run(chesscom.fetch_archives("hikaru"))


def test_fetch_archives_reports_unknown_user(monkeypatch):
    url = "https://api.chess.com/pub/player/missing-user/games/archives"
    response = _response(404, url, text="Not Found")
    monkeypatch.setattr(chesscom, "build_client", lambda: DummyClient(response))

    with pytest.raises(ValueError, match="not found"):
        asyncio.run(chesscom.fetch_archives("missing-user"))
