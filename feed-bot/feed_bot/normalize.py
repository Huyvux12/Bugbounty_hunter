from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from feed_bot.classify import classify_kind, is_concrete
from feed_bot.models import Asset, Program

_HANDLE_RE = re.compile(r"[^a-z0-9]+")


def slug(value: str) -> str:
    text = _HANDLE_RE.sub("-", (value or "").strip().lower()).strip("-")
    return text or "unknown"


def _money(value: Any) -> tuple[float | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, dict):
        amount, _nested_currency = _money(value.get("value"))
        return amount, value.get("currency") or _nested_currency
    try:
        return float(value), None
    except (TypeError, ValueError):
        return None, None


def _asset(
    identifier: str,
    asset_type: str,
    in_scope: bool,
    eligible_for_submission: bool | None = None,
    eligible_for_bounty: bool | None = None,
) -> Asset:
    ident = (identifier or "").strip()
    kind = classify_kind(ident, asset_type)
    return Asset(
        identifier=ident,
        asset_type=asset_type or "other",
        in_scope=in_scope,
        kind=kind,
        eligible_for_submission=eligible_for_submission,
        eligible_for_bounty=eligible_for_bounty,
    )


def _finish(program: Program) -> Program:
    program.concrete_count = sum(1 for a in program.in_scope if is_concrete(a.kind))
    return program


def normalize_hackerone(raw: dict[str, Any], source: str = "arkadiyt") -> Program | None:
    handle = str(raw.get("handle") or slug(str(raw.get("name") or "")))
    targets = raw.get("targets") or {}
    in_scope = []
    for item in targets.get("in_scope") or []:
        in_scope.append(
            _asset(
                str(item.get("asset_identifier") or item.get("identifier") or ""),
                str(item.get("asset_type") or "URL"),
                True,
                item.get("eligible_for_submission"),
                item.get("eligible_for_bounty"),
            )
        )
    out_scope = []
    for item in targets.get("out_of_scope") or []:
        out_scope.append(
            _asset(
                str(item.get("asset_identifier") or item.get("identifier") or ""),
                str(item.get("asset_type") or "URL"),
                False,
                item.get("eligible_for_submission"),
                item.get("eligible_for_bounty"),
            )
        )
    status = str(raw.get("submission_state") or raw.get("state") or "open").lower()
    return _finish(
        Program(
            id=f"hackerone:{handle}",
            platform="hackerone",
            handle=handle,
            name=str(raw.get("name") or handle),
            url=str(raw.get("url") or f"https://hackerone.com/{handle}"),
            offers_bounty=bool(raw.get("offers_bounties") or raw.get("offers_bounty")),
            status=status,
            source=source,
            visibility="public" if source == "arkadiyt" else "access-scoped",
            in_scope=in_scope,
            out_of_scope=out_scope,
        )
    )


def normalize_bugcrowd(raw: dict[str, Any], source: str = "arkadiyt") -> Program | None:
    url = str(raw.get("url") or "")
    handle = _handle_from_url(url) or slug(str(raw.get("name") or "bugcrowd"))
    targets = raw.get("targets") or {}
    in_scope = [
        _asset(str(i.get("target") or i.get("uri") or i.get("name") or ""), str(i.get("type") or "website"), True)
        for i in targets.get("in_scope") or []
    ]
    out_scope = [
        _asset(str(i.get("target") or i.get("uri") or i.get("name") or ""), str(i.get("type") or "website"), False)
        for i in targets.get("out_of_scope") or []
    ]
    max_payout, _ = _money(raw.get("max_payout"))
    return _finish(
        Program(
            id=f"bugcrowd:{handle}",
            platform="bugcrowd",
            handle=handle,
            name=str(raw.get("name") or handle),
            url=url or f"https://bugcrowd.com/{handle}",
            offers_bounty=bool(max_payout and max_payout > 0),
            status="open",
            source=source,
            visibility="public" if source == "arkadiyt" else "access-scoped",
            in_scope=in_scope,
            out_of_scope=out_scope,
            max_bounty=max_payout,
            currency="USD",
        )
    )


def normalize_intigriti(raw: dict[str, Any], source: str = "arkadiyt") -> Program | None:
    handle = str(raw.get("handle") or raw.get("company_handle") or slug(str(raw.get("name") or "")))
    confidentiality = str(raw.get("confidentiality_level") or "public").lower()
    if confidentiality not in {"public", "", "unknown"} and source == "arkadiyt":
        return None
    targets = raw.get("targets") or {}
    in_scope = [
        _asset(str(i.get("endpoint") or i.get("target") or ""), str(i.get("type") or "url"), True)
        for i in targets.get("in_scope") or []
    ]
    out_scope = [
        _asset(str(i.get("endpoint") or i.get("target") or ""), str(i.get("type") or "url"), False)
        for i in targets.get("out_of_scope") or []
    ]
    min_b, currency = _money(raw.get("min_bounty"))
    max_b, currency2 = _money(raw.get("max_bounty"))
    status = str(raw.get("status") or "open").lower()
    return _finish(
        Program(
            id=f"intigriti:{handle}",
            platform="intigriti",
            handle=handle,
            name=str(raw.get("name") or handle),
            url=str(raw.get("url") or f"https://www.intigriti.com/programs/{handle}/{handle}/detail"),
            offers_bounty=bool((max_b or 0) > 0 or (min_b or 0) > 0),
            status=status,
            source=source,
            visibility="public" if confidentiality in {"public", ""} else "access-scoped",
            in_scope=in_scope,
            out_of_scope=out_scope,
            min_bounty=min_b,
            max_bounty=max_b,
            currency=currency or currency2 or "EUR",
        )
    )


def normalize_yeswehack(raw: dict[str, Any], source: str = "arkadiyt") -> Program | None:
    if raw.get("public") is False and source == "arkadiyt":
        return None
    handle = str(raw.get("id") or slug(str(raw.get("name") or "")))
    if raw.get("disabled"):
        status = "disabled"
    else:
        status = "open"
    targets = raw.get("targets") or {}
    in_scope = [
        _asset(str(i.get("target") or ""), str(i.get("type") or "web-application"), True)
        for i in targets.get("in_scope") or []
    ]
    out_scope = [
        _asset(str(i.get("target") or ""), str(i.get("type") or "other"), False)
        for i in targets.get("out_of_scope") or []
    ]
    min_b, _ = _money(raw.get("min_bounty"))
    max_b, _ = _money(raw.get("max_bounty"))
    return _finish(
        Program(
            id=f"yeswehack:{handle}",
            platform="yeswehack",
            handle=handle,
            name=str(raw.get("name") or handle),
            url=str(raw.get("url") or f"https://yeswehack.com/programs/{handle}"),
            offers_bounty=bool((max_b or 0) > 0 or (min_b or 0) > 0),
            status=status,
            source=source,
            visibility="public" if raw.get("public", True) else "access-scoped",
            in_scope=in_scope,
            out_of_scope=out_scope,
            min_bounty=min_b,
            max_bounty=max_b,
            currency="EUR",
        )
    )


def normalize_federacy(raw: dict[str, Any], source: str = "arkadiyt") -> Program | None:
    url = str(raw.get("url") or "")
    handle = _handle_from_url(url) or slug(str(raw.get("name") or "federacy"))
    targets = raw.get("targets") or {}
    in_scope = [
        _asset(str(i.get("target") or ""), str(i.get("type") or "website"), True)
        for i in targets.get("in_scope") or []
    ]
    out_scope = [
        _asset(str(i.get("target") or ""), str(i.get("type") or "website"), False)
        for i in targets.get("out_of_scope") or []
    ]
    return _finish(
        Program(
            id=f"federacy:{handle}",
            platform="federacy",
            handle=handle,
            name=str(raw.get("name") or handle),
            url=url or f"https://www.federacy.com/{handle}",
            offers_bounty=bool(raw.get("offers_awards") or raw.get("offers_bounty")),
            status="open",
            source=source,
            visibility="public",
            in_scope=in_scope,
            out_of_scope=out_scope,
        )
    )


def normalize_hackenproof(raw: dict[str, Any], source: str = "hackenproof_mcp") -> Program | None:
    if raw.get("error"):
        return None
    status_obj = raw.get("status")
    status_name = ""
    if isinstance(status_obj, dict):
        status_name = str(status_obj.get("name") or "").lower()
    elif status_obj:
        status_name = str(status_obj).lower()
    state = str(raw.get("state") or status_name or "published").lower()
    if state in {"archived", "disabled", "draft"} or status_name in {"archived", "disabled"}:
        return None
    handle = str(
        raw.get("program") or raw.get("slug") or raw.get("handle") or slug(str(raw.get("name") or raw.get("title") or ""))
    )
    name = str(raw.get("title") or raw.get("name") or handle)
    url = str(raw.get("url") or f"https://hackenproof.com/programs/{handle}")
    in_scope, out_scope = _hackenproof_scopes(raw)
    rewards = raw.get("rewards") if isinstance(raw.get("rewards"), dict) else {}
    max_b, currency = _money(raw.get("max_bounty") or raw.get("max_reward"))
    min_b, currency2 = _money(raw.get("min_bounty") or raw.get("min_reward"))
    if max_b is None:
        max_b, _ = _money(
            rewards.get("critical_max") or rewards.get("high_max") or rewards.get("medium_max") or rewards.get("low_max")
        )
    if min_b is None:
        min_b, _ = _money(
            rewards.get("low_min") or rewards.get("medium_min") or rewards.get("high_min") or rewards.get("critical_min")
        )
    offers = bool((max_b or 0) > 0 or (min_b or 0) > 0 or raw.get("offers_bounty"))
    live = state in {"live", "open", "active", "published", ""} or status_name == "active"
    return _finish(
        Program(
            id=f"hackenproof:{handle}",
            platform="hackenproof",
            handle=handle,
            name=name,
            url=url,
            offers_bounty=offers,
            status="open" if live else state,
            source=source,
            visibility="public",
            in_scope=in_scope,
            out_of_scope=out_scope,
            min_bounty=min_b,
            max_bounty=max_b,
            currency=currency or currency2 or "USD",
        )
    )


def _hackenproof_scopes(raw: dict[str, Any]) -> tuple[list[Asset], list[Asset]]:
    in_scope: list[Asset] = []
    out_scope: list[Asset] = []
    info = raw.get("program") if isinstance(raw.get("program"), dict) else raw
    scopes = info.get("scopes") if isinstance(info, dict) else None
    if scopes is None:
        targets = info.get("targets") if isinstance(info, dict) else None
        if isinstance(targets, dict):
            for item in targets.get("in_scope") or []:
                in_scope.append(_hp_asset(item, True))
            for item in targets.get("out_of_scope") or []:
                out_scope.append(_hp_asset(item, False))
            return in_scope, out_scope
        scopes = []
    if isinstance(scopes, dict):
        for item in scopes.get("in_scope") or scopes.get("inScope") or []:
            in_scope.append(_hp_asset(item, True))
        for item in scopes.get("out_of_scope") or scopes.get("outOfScope") or []:
            out_scope.append(_hp_asset(item, False))
        return in_scope, out_scope
    for item in scopes or []:
        if not isinstance(item, dict):
            continue
        out = bool(item.get("out_of_scope") or item.get("outOfScope"))
        asset = _hp_asset(item, not out)
        (out_scope if out else in_scope).append(asset)
    return in_scope, out_scope


def _hp_asset(item: dict[str, Any], in_scope: bool) -> Asset:
    description = str(item.get("target_description") or "").strip()
    target = str(item.get("target") or item.get("endpoint") or item.get("identifier") or item.get("asset") or "").strip()
    identifier = description if _looks_like_host(description) else target or description
    asset_type = str(item.get("type") or item.get("title") or item.get("asset_type") or "Web")
    return _asset(identifier, asset_type, in_scope)


def _looks_like_host(value: str) -> bool:
    text = value.lower().strip()
    if not text:
        return False
    return text.startswith("http://") or text.startswith("https://") or "." in text.split()[0]


def _handle_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return ""
    parts = [p for p in path.split("/") if p and p not in {"engagements", "programs"}]
    return slug(parts[-1]) if parts else ""


NORMALIZERS = {
    "hackerone": normalize_hackerone,
    "bugcrowd": normalize_bugcrowd,
    "intigriti": normalize_intigriti,
    "yeswehack": normalize_yeswehack,
    "federacy": normalize_federacy,
    "hackenproof": normalize_hackenproof,
}


def normalize_many(platform: str, rows: list[dict[str, Any]], source: str) -> list[Program]:
    fn = NORMALIZERS[platform]
    programs: list[Program] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        program = fn(row, source=source)
        if program and program.id:
            programs.append(program)
    return programs
