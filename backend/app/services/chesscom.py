from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.config import settings
from app.models.schemas import ArchiveModel


BASE = "https://api.chess.com/pub/player"


def get_ssl_verify_setting() -> bool | str:
    if settings.chesscom_ca_bundle:
        return settings.chesscom_ca_bundle
    return settings.chesscom_ssl_verify


def build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=15.0,
        verify=get_ssl_verify_setting(),
        headers={
            "User-Agent": settings.chesscom_user_agent,
            "Accept": "application/json",
        },
    )


async def fetch_archives(username: str) -> list[ArchiveModel]:
    normalized_username = username.strip().lower()
    url = f"{BASE}/{normalized_username}/games/archives"
    async with build_client() as client:
        response = await client.get(url)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code == 403:
                body_preview = response.text[:500].lower()
                if "web filter violation" in body_preview or "trend micro" in body_preview:
                    raise ValueError(
                        "Blocked by network web filter before reaching Chess.com. "
                        "Configure HTTP(S)_PROXY for the backend container or ask IT to allow "
                        "api.chess.com."
                    ) from exc
                raise ValueError(
                    "Chess.com returned 403 Forbidden. This is usually network/proxy blocking "
                    "or anti-bot filtering. Try again with a different network or set a custom "
                    "CHESSCOM_USER_AGENT."
                ) from exc
            raise
        data = response.json()

    archives = []
    for archive_url in data.get("archives", []):
        parsed = urlparse(archive_url)
        chunks = [c for c in parsed.path.split("/") if c]
        year, month = int(chunks[-2]), int(chunks[-1])
        archives.append(ArchiveModel(year=year, month=month, url=archive_url))

    archives.sort(key=lambda x: (x.year, x.month), reverse=True)
    return archives


async def fetch_game_pgn(archive_url: str, game_index: int) -> str:
    async with build_client() as client:
        response = await client.get(archive_url)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code == 403:
                body_preview = response.text[:500].lower()
                if "web filter violation" in body_preview or "trend micro" in body_preview:
                    raise ValueError(
                        "Blocked by network web filter while fetching archive games. "
                        "Configure HTTP(S)_PROXY for backend container or ask IT to allow "
                        "api.chess.com."
                    ) from exc
                raise ValueError(
                    "Chess.com returned 403 Forbidden while fetching games from archive."
                ) from exc
            raise
        data = response.json()

    games = data.get("games", [])
    if game_index < 0 or game_index >= len(games):
        raise ValueError("game_index out of range")

    pgn = games[game_index].get("pgn")
    if not pgn:
        raise ValueError("Selected game has no PGN")
    return pgn
