from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from feed_bot.validation import string_list
from feed_bot.sources.result import FetchBatch

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
        statuses = []
        loaders = (
            ("lissy93", LISSY_URL, lambda r: _from_lissy(r.text)),
            ("projectdiscovery", PD_URL, lambda r: _from_pd(r.json())),
            ("diodb", DIODB_URL, lambda r: _from_diodb(r.json())),
        )
        for name, url, parse in loaders:
            try:
                batch = parse(_get(http, url))
                rows.extend(batch)
                statuses.append({"source": name, "ok": True, "count": len(batch)})
            except Exception as exc:
                statuses.append({"source": name, "ok": False, "error": str(exc)})
        merged = _merge(rows)
        extra = max(0, len(merged) - MAX_PROGRAMS)
        if extra:
            # Cap is a ranked trim, not a fetch failure: overflow drops instead of going stale.
            statuses.append({"source": "limit", "ok": True, "count": MAX_PROGRAMS, "truncated": extra})
        return FetchBatch(merged[:MAX_PROGRAMS], complete=all(s["ok"] for s in statuses), sources=statuses)
    finally:
        if own:
            http.close()


def _get(http: httpx.Client, url: str) -> httpx.Response:
    response = http.get(url)
    response.raise_for_status()
    return response


def _from_diodb(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("diodb response must be a list")
    rows = payload
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
    if not isinstance(programs, list):
        raise ValueError("ProjectDiscovery programs must be a list")
    out = []
    for item in programs:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or _is_platform(url):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        domains = string_list(item.get("domains"), "domains")
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
    payload = yaml.safe_load(text)
    companies = payload.get("companies") if isinstance(payload, dict) else None
    if not isinstance(companies, list):
        raise ValueError("lissy93 companies must be a list")
    rows = []
    aliases = {"company": "name", "description": "summary", "min_payout": "min_bounty", "max_payout": "max_bounty"}
    for item in companies:
        if not isinstance(item, dict):
            raise ValueError("lissy93 company must be an object")
        row = {aliases.get(key, key): value for key, value in item.items()}
        for field in ("domains", "out_of_scope"):
            row[field] = string_list(row.get(field), field)
        row["source_dump"] = "lissy93"
        row["policy_url"] = row.get("url")
        if row.get("url") and row.get("name") and not _is_platform(str(row["url"])):
            rows.append(row)
    return rows


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
