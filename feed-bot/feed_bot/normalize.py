from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from feed_bot.validation import money, string_list
from feed_bot.classify import classify_kind, is_concrete
from feed_bot.models import Asset, Program
from feed_bot.rewards import attach_derived, infer_reward_types
from feed_bot.sources.selfhost import _dedupe_key, _is_http_url, _is_platform, SHARED_POLICY_HOSTS

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
    return money(value), None


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
    if program.min_bounty is not None and program.max_bounty is not None and program.min_bounty > program.max_bounty:
        program.min_bounty = program.max_bounty = None
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


def normalize_self_host(raw: dict[str, Any], source: str = "selfhost_dump") -> Program | None:
    url = str(raw.get("url") or raw.get("policy_url") or "").strip()
    name = str(raw.get("name") or raw.get("program_name") or "").strip()
    if not _is_http_url(url) or not name or _is_platform(url):
        return None
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    handle = slug(_dedupe_key(raw) if host in SHARED_POLICY_HOSTS else host or name)
    domains = string_list(raw.get("domains"), "domains")
    in_scope = []
    for domain in domains:
        text = str(domain).strip()
        if not text:
            continue
        in_scope.append(_asset(text, "WILDCARD" if "*" in text else "DOMAIN", True))
    status = str(raw.get("status") or "open").lower()
    if status in {"paused", "closed", "disabled"}:
        status = "paused"
    elif status in {"open", "active", "live", "published"}:
        status = "open"
    else:
        status = "unknown" if not status else status
    min_b, _ = _money(raw.get("min_bounty") or raw.get("min_payout"))
    max_b, _ = _money(raw.get("max_bounty") or raw.get("max_payout"))
    rewards = infer_reward_types(raw)
    program = Program(
        id=f"self-host:{handle}",
        platform="self-host",
        handle=handle,
        name=name,
        url=url,
        offers_bounty="cash" in rewards or "crypto" in rewards,
        status=status,
        source=str(raw.get("source_dump") or source),
        visibility="public",
        in_scope=in_scope,
        out_of_scope=[
            _asset(str(value).strip(), "other", False)
            for value in string_list(raw.get("out_of_scope"), "out_of_scope")
        ],
        min_bounty=min_b,
        max_bounty=max_b,
        currency=str(raw.get("currency") or "") or None,
        reward_types=rewards,
        summary=str(raw.get("summary") or raw.get("description") or "") or None,
        policy_url=str(raw.get("policy_url") or url) or None,
        contact=str(raw.get("contact") or "") or None,
    )
    return _finish(program)


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
    "self-host": normalize_self_host,
}


def normalize_many(platform: str, rows: list[dict[str, Any]], source: str) -> list[Program]:
    fn = NORMALIZERS[platform]
    programs: list[Program] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        program = fn(row, source=source)
        if program and program.id:
            if not program.reward_types:
                program.reward_types = infer_reward_types(row, offers_bounty=program.offers_bounty)
            attach_derived(program)
            programs.append(program)
    return programs
