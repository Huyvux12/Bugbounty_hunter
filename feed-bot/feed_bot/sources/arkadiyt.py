from __future__ import annotations

from typing import Any

import httpx

ARKADIYT_BASE = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/master/data"
DUMP_FILES = {
    "hackerone": "hackerone_data.json",
    "bugcrowd": "bugcrowd_data.json",
    "intigriti": "intigriti_data.json",
    "yeswehack": "yeswehack_data.json",
    "federacy": "federacy_data.json",
}


class SourceError(Exception):
    def __init__(self, platform: str, message: str):
        super().__init__(message)
        self.platform = platform
        self.message = message


def fetch_dump(platform: str, timeout: float = 120.0, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    filename = DUMP_FILES[platform]
    url = f"{ARKADIYT_BASE}/{filename}"
    own = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        response = http.get(url)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise SourceError(platform, f"arkadiyt {filename}: {exc}") from exc
    finally:
        if own:
            http.close()
    if not isinstance(payload, list):
        raise SourceError(platform, f"arkadiyt {filename} is not a list")
    return [row for row in payload if isinstance(row, dict)]
