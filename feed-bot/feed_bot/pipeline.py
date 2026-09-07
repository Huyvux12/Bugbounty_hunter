from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from feed_bot.diff import diff_snapshot, stamp
from feed_bot.models import Program
from feed_bot.normalize import normalize_many
from feed_bot.rank import build_feeds
from feed_bot.llm import copy_cached_llm, enrich_selfhost
from feed_bot.rewards import attach_derived
from feed_bot.sources.arkadiyt import DUMP_FILES, SourceError, fetch_dump
from feed_bot.sources.hackenproof import fetch_hackenproof
from feed_bot.sources.selfhost import fetch_selfhost
from feed_bot.store import default_data_dir, default_docs_dir, load_previous, publish_docs, save_snapshot
from feed_bot.telegram import send_digest

DumpFetcher = Callable[[str], list[dict[str, Any]]]
HpFetcher = Callable[[], list[dict[str, Any]]]
SelfhostFetcher = Callable[[], list[dict[str, Any]]]


def run(
    data_dir: Path | None = None,
    docs_dir: Path | None = None,
    now: datetime | None = None,
    fetch_dump_fn: DumpFetcher = fetch_dump,
    fetch_hackenproof_fn: HpFetcher = fetch_hackenproof,
    fetch_selfhost_fn: SelfhostFetcher = fetch_selfhost,
    send_telegram: bool = True,
    enrich_llm: bool = True,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    data_dir = data_dir or default_data_dir()
    docs_dir = docs_dir or default_docs_dir()
    previous = load_previous(data_dir)
    programs: list[Program] = []
    source_status: list[dict[str, Any]] = []

    for platform in DUMP_FILES:
        try:
            rows = fetch_dump_fn(platform)
            batch = normalize_many(platform, rows, source="arkadiyt")
            programs.extend(batch)
            source_status.append({"platform": platform, "ok": True, "count": len(batch), "via": "arkadiyt"})
        except Exception as exc:
            source_status.append(
                {
                    "platform": platform,
                    "ok": False,
                    "via": "arkadiyt",
                    "error": str(exc),
                }
            )

    try:
        hp_rows = fetch_hackenproof_fn()
        batch = normalize_many("hackenproof", hp_rows, source="hackenproof_mcp")
        programs.extend(batch)
        source_status.append({"platform": "hackenproof", "ok": True, "count": len(batch), "via": "mcp"})
    except SourceError as exc:
        source_status.append({"platform": "hackenproof", "ok": False, "via": "mcp", "error": exc.message})
    except Exception as exc:
        source_status.append({"platform": "hackenproof", "ok": False, "via": "mcp", "error": str(exc)})

    try:
        sh_rows = fetch_selfhost_fn()
        batch = normalize_many("self-host", sh_rows, source="selfhost_dump")
        programs.extend(batch)
        source_status.append({"platform": "self-host", "ok": True, "count": len(batch), "via": "dumps"})
    except SourceError as exc:
        source_status.append({"platform": "self-host", "ok": False, "via": "dumps", "error": exc.message})
    except Exception as exc:
        source_status.append({"platform": "self-host", "ok": False, "via": "dumps", "error": str(exc)})

    programs = _dedupe(programs)
    programs = stamp(programs, previous, now)
    copy_cached_llm(programs, previous)
    llm_used = 0
    if enrich_llm:
        try:
            llm_used = enrich_selfhost(programs)
        except Exception as exc:
            source_status.append({"platform": "llm", "ok": False, "via": "openai-compat", "error": str(exc)})
    for program in programs:
        attach_derived(program)
    feeds = build_feeds(programs, now, has_history=bool(previous))
    diff = diff_snapshot(programs, previous)
    generated_at = feeds["generated_at"]
    save_snapshot(data_dir, programs, feeds, diff, source_status, generated_at)
    pages_url = os.environ.get("PAGES_URL")
    publish_docs(docs_dir, data_dir, feeds, generated_at, pages_url)
    telegram_sent = False
    telegram_error = None
    if send_telegram:
        try:
            telegram_sent = send_digest(feeds, diff, source_status, pages_url=pages_url)
        except Exception as exc:
            telegram_error = str(exc)
    return {
        "count": len(programs),
        "feeds": feeds,
        "diff": diff,
        "source_status": source_status,
        "telegram_sent": telegram_sent,
        "telegram_error": telegram_error,
        "llm_used": llm_used,
    }


def _dedupe(programs: list[Program]) -> list[Program]:
    by_id: dict[str, Program] = {}
    for program in programs:
        existing = by_id.get(program.id)
        if existing is None or _source_rank(program) < _source_rank(existing):
            by_id[program.id] = program
    return list(by_id.values())


def _source_rank(program: Program) -> int:
    order = {
        "arkadiyt": 0,
        "hackenproof_mcp": 1,
        "lissy93": 2,
        "projectdiscovery": 3,
        "diodb": 4,
        "selfhost_dump": 5,
    }
    return order.get(program.source, 6)
