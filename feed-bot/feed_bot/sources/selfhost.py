from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from feed_bot.sources.arkadiyt import SourceError

DIODB_URL = "https://raw.githubusercontent.com/disclose/diodb/master/program-list.json"
PD_URL = "https://raw.githubusercontent.com/projectdiscovery/public-bugbounty-programs/main/dist/data.json"
LISSY_URL = "https://raw.githubusercontent.com/Lissy93/bug-bounties/main/independent-programs.yml"
MAX_PROGRAMS = 500
PLATFORM_HOSTS = (
    "hackerone.com",
    "bugcrowd.com",
    "intigriti.com",
    "yeswehack.com",
    "federacy.com",
    "hackenproof.com",
    "synack.com",
    "openbugbounty.org",
    "yogosha.com",
    "hacktify.eu",
    "app.intigriti.com",
)


def fetch_selfhost(client: httpx.Client | None = None) -> list[dict[str, Any]]:
    own = client is None
    http = client or httpx.Client(timeout=90.0, follow_redirects=True)
    try:
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        try:
            rows.extend(_from_lissy(_get(http, LISSY_URL).text))
        except Exception as exc:
            errors.append(f"lissy93: {exc}")
        try:
            payload = _get(http, PD_URL).json()
            rows.extend(_from_pd(payload))
        except Exception as exc:
            errors.append(f"projectdiscovery: {exc}")
        try:
            payload = _get(http, DIODB_URL).json()
            rows.extend(_from_diodb(payload))
        except Exception as exc:
            errors.append(f"diodb: {exc}")
        if not rows:
            raise SourceError("self-host", "; ".join(errors) or "no self-host dumps")
        return _merge(rows)[:MAX_PROGRAMS]
    finally:
        if own:
            http.close()


def _get(http: httpx.Client, url: str) -> httpx.Response:
    response = http.get(url)
    response.raise_for_status()
    return response


def _from_diodb(payload: Any) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        if str(item.get("policy_url_status") or "").lower() == "dead":
            continue
        url = str(item.get("policy_url") or item.get("contact_url") or "").strip()
        if not url or _is_platform(url) or _is_platform(str(item.get("contact_url") or "")):
            continue
        name = str(item.get("program_name") or "").strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "url": url,
                "policy_url": url,
                "contact": str(item.get("contact_email") or item.get("contact_url") or ""),
                "offers_bounty": item.get("offers_bounty"),
                "offers_swag": item.get("offers_swag"),
                "hall_of_fame": item.get("hall_of_fame"),
                "domains": [],
                "source_dump": "diodb",
            }
        )
    return out


def _from_pd(payload: Any) -> list[dict[str, Any]]:
    programs = payload.get("programs") if isinstance(payload, dict) else payload
    out = []
    for item in programs or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or _is_platform(url):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        domains = [str(d) for d in (item.get("domains") or []) if d]
        out.append(
            {
                "name": name,
                "url": url,
                "policy_url": url,
                "offers_bounty": item.get("bounty"),
                "offers_swag": item.get("swag"),
                "domains": domains,
                "source_dump": "projectdiscovery",
            }
        )
    return out


def _from_lissy(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    list_key: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("- company:"):
            if current and current.get("url"):
                out.append(current)
            current = {
                "name": line.split(":", 1)[1].strip().strip("'\""),
                "source_dump": "lissy93",
            }
            list_key = None
            continue
        if current is None or not line.startswith("  "):
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and list_key:
            current.setdefault(list_key, []).append(stripped[2:].strip().strip("'\""))
            continue
        if ":" not in stripped or stripped.startswith("- "):
            continue
        key, value = stripped.split(":", 1)
        value = value.strip().strip("'\"")
        if value == "" or value == "|-" or value == "|":
            list_key = key
            if key in {"rewards", "domains", "out_of_scope"}:
                current[key] = []
            continue
        list_key = None
        if key == "url":
            current["url"] = value
            current["policy_url"] = value
        elif key == "contact":
            current["contact"] = value
        elif key == "description":
            current["summary"] = value
        elif key == "min_payout":
            current["min_bounty"] = value
        elif key == "max_payout":
            current["max_bounty"] = value
        elif key == "currency":
            current["currency"] = value
        elif key == "status":
            current["status"] = value
        elif key == "program_type":
            current["program_type"] = value
        else:
            current[key] = value
    if current and current.get("url"):
        out.append(current)
    return [row for row in out if not _is_platform(str(row.get("url") or ""))]


def _merge(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {"lissy93": 0, "projectdiscovery": 1, "diodb": 2}
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _dedupe_key(row)
        existing = by_key.get(key)
        if existing is None or rank.get(row.get("source_dump"), 9) < rank.get(existing.get("source_dump"), 9):
            by_key[key] = row
        elif existing is not None:
            if not existing.get("domains") and row.get("domains"):
                existing["domains"] = row["domains"]
            if not existing.get("contact") and row.get("contact"):
                existing["contact"] = row["contact"]
    merged = list(by_key.values())

    def sort_key(item: dict[str, Any]) -> tuple:
        bounty = str(item.get("offers_bounty") or item.get("program_type") or "").lower()
        cash = bounty in {"true", "yes", "1", "bounty", "hybrid"}
        swag = str(item.get("offers_swag") or "").lower() in {"true", "yes", "1"}
        return (0 if cash else 1, 0 if swag else 1, str(item.get("name") or "").lower())

    merged.sort(key=sort_key)
    return merged


def _dedupe_key(row: dict[str, Any]) -> str:
    host = urlparse(str(row.get("url") or "")).hostname or ""
    host = host.lower().removeprefix("www.")
    if host:
        return host
    return str(row.get("name") or "").strip().lower()


def _is_platform(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == p or host.endswith("." + p) for p in PLATFORM_HOSTS)
