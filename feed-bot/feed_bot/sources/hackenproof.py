from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from feed_bot.mcp_client import McpHttpClient, as_rows
from feed_bot.sources.arkadiyt import SourceError

DEFAULT_URL = "https://mcp.hackenproof.com/mcp"
MAX_PROGRAMS = 200
PD_PROGRAMS_URL = (
    "https://raw.githubusercontent.com/projectdiscovery/public-bugbounty-programs/main/dist/data.json"
)
WATCHLIST = Path(__file__).resolve().parents[2] / "watchlists" / "hackenproof_slugs.txt"


def fetch_hackenproof(
    api_key: str | None = None,
    url: str | None = None,
    client_factory: Callable[[], Any] | None = None,
    slugs: list[str] | None = None,
    discover: bool = True,
) -> list[dict[str, Any]]:
    key = api_key if api_key is not None else os.environ.get("HACKENPROOF_API_KEY")
    if not key:
        raise SourceError("hackenproof", "HACKENPROOF_API_KEY missing")

    def _make() -> Any:
        if client_factory:
            return client_factory()
        mcp = McpHttpClient(url or os.environ.get("HACKENPROOF_MCP_URL") or DEFAULT_URL, {"X-Api-Key": key})
        mcp.initialize()
        return mcp

    try:
        mcp = _make()
        found: dict[str, dict[str, Any]] = {}

        for company in as_rows(_call(mcp, "list_companies", {})):
            company_slug = str(company.get("slug") or company.get("handle") or "")
            if not company_slug:
                continue
            programs = as_rows(_call(mcp, "list_programs", {"company": company_slug}))
            for program in programs:
                slug = _slug_of(program)
                if slug:
                    found[slug] = {"slug": slug, "company": company_slug}

        wanted = list(dict.fromkeys(slugs if slugs is not None else _discover_slugs(discover)))
        for slug in wanted:
            found.setdefault(slug, {"slug": slug})

        if not found:
            raise SourceError(
                "hackenproof",
                "MCP list_companies empty and no slugs in watchlist/ProjectDiscovery",
            )

        hydrated: list[dict[str, Any]] = []
        for slug, meta in list(found.items())[:MAX_PROGRAMS]:
            info = _call(mcp, "get_program_info", {"program": slug})
            if not isinstance(info, dict) or info.get("error"):
                continue
            merged = dict(meta)
            merged.update(info)
            merged["slug"] = str(info.get("program") or slug)
            hydrated.append(merged)
        return hydrated
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError("hackenproof", f"MCP: {exc}") from exc


def _call(mcp: Any, name: str, arguments: dict[str, Any]) -> Any:
    return mcp.call_tool(name, arguments)


def _slug_of(program: dict[str, Any]) -> str:
    return str(program.get("slug") or program.get("program") or program.get("handle") or program.get("id") or "").strip()


def _discover_slugs(enabled: bool) -> list[str]:
    slugs: list[str] = []
    slugs.extend(_read_watchlist())
    if enabled:
        slugs.extend(_slugs_from_projectdiscovery())
    return list(dict.fromkeys(s for s in slugs if s))


def _read_watchlist(path: Path = WATCHLIST) -> list[str]:
    if not path.is_file():
        return []
    slugs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        slugs.append(_slug_from_url(text) or text)
    return slugs


def _slugs_from_projectdiscovery() -> list[str]:
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            payload = client.get(PD_PROGRAMS_URL).json()
    except Exception:
        return []
    programs = payload.get("programs") if isinstance(payload, dict) else payload
    slugs = []
    for row in programs or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "")
        if "hackenproof.com" not in url:
            continue
        slug = _slug_from_url(url)
        if slug:
            slugs.append(slug)
    return slugs


def _slug_from_url(url: str) -> str:
    if "hackenproof.com" not in url and "/" not in url:
        return url.strip()
    path = urlparse(url).path.strip("/")
    if not path:
        return ""
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] == "programs" and len(parts) >= 2:
        return parts[1]
    return parts[-1]
