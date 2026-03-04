from __future__ import annotations

import argparse
import asyncio
import os
import sys

import httpx

from app.services.chesscom import BASE, build_client, fetch_archives, get_ssl_verify_setting, normalize_username


def _proxy_snapshot() -> dict[str, str]:
    return {
        "HTTP_PROXY": os.getenv("HTTP_PROXY", ""),
        "HTTPS_PROXY": os.getenv("HTTPS_PROXY", ""),
        "NO_PROXY": os.getenv("NO_PROXY", ""),
        "http_proxy": os.getenv("http_proxy", ""),
        "https_proxy": os.getenv("https_proxy", ""),
        "no_proxy": os.getenv("no_proxy", ""),
    }


async def _run_probe(username: str) -> int:
    normalized = normalize_username(username)
    verify = get_ssl_verify_setting()
    proxies = _proxy_snapshot()

    print("== Chess.com Connectivity Probe ==")
    print(f"username={normalized}")
    print(f"verify={verify!r}")
    print("proxy_env:")
    for key, value in proxies.items():
        redacted = "<set>" if value else "<empty>"
        print(f"  {key}={redacted}")

    url = f"{BASE}/{normalized}/games/archives"
    print(f"probe_url={url}")

    async with build_client() as client:
        try:
            response = await client.get(url)
            print(f"http_status={response.status_code}")
            body_preview = (response.text or "").replace("\n", " ")[:220]
            print(f"body_preview={body_preview}")
        except httpx.HTTPError as exc:
            print(f"http_error={type(exc).__name__}: {exc}")
            return 2

    try:
        archives = await fetch_archives(normalized)
    except Exception as exc:  # noqa: BLE001 - operator-facing probe output.
        print(f"fetch_archives_error={type(exc).__name__}: {exc}")
        return 1

    print(f"archives_count={len(archives)}")
    for archive in archives[:5]:
        print(f"archive={archive.year}-{archive.month:02d} url={archive.url}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Chess.com API connectivity from backend runtime.")
    parser.add_argument("--username", default="hikaru", help="Chess.com username or profile URL")
    args = parser.parse_args()
    return asyncio.run(_run_probe(args.username))


if __name__ == "__main__":
    sys.exit(main())
