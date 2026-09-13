from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from feed_bot.diff import diff_snapshot, stamp, append_history
from feed_bot.models import Program
from feed_bot.normalize import normalize_many
from feed_bot.rank import build_feeds
from feed_bot.llm import copy_cached_llm, enrich_selfhost
from feed_bot.rewards import attach_derived
from feed_bot.sources.arkadiyt import DUMP_FILES, fetch_dump
from feed_bot.sources.hackenproof import fetch_hackenproof
from feed_bot.sources.selfhost import fetch_selfhost
from feed_bot.store import default_data_dir, default_docs_dir, publish_docs, save_snapshot
from feed_bot.telegram import send_digest
from feed_bot.storage import load_state, atomic_json
from feed_bot.outbox import enqueue, flush

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
    state = load_state(data_dir)
    previous = {row["id"]: Program.from_dict(row) for row in state["programs"]}
    programs: list[Program] = []
    source_status: list[dict[str, Any]] = []
    fetchers = [(platform, "arkadiyt", lambda p=platform: fetch_dump_fn(p)) for platform in DUMP_FILES]
    fetchers += [("hackenproof", "hackenproof_mcp", fetch_hackenproof_fn), ("self-host", "selfhost_dump", fetch_selfhost_fn)]
    for platform, source, fetch in fetchers:
        status = {"platform": platform, "via": {"hackenproof_mcp": "mcp", "selfhost_dump": "dumps"}.get(source, source),
                  "ok": True, "state": "complete", "count": 0, "rejected_count": 0, "skipped_count": 0, "retained_count": 0}
        batch = []
        try:
            rows = fetch()
            if not isinstance(rows, list):
                raise ValueError("source response must be a list")
            complete = getattr(rows, "complete", True)
            status["sources"] = getattr(rows, "sources", [])
            status["rejected_count"] = getattr(rows, "rejected_count", 0)
            status["input_count"] = len(rows) + status["rejected_count"]
            for row in rows:
                try:
                    if not isinstance(row, dict):
                        raise ValueError("program must be an object")
                    normalized = normalize_many(platform, [row], source=source)
                    batch.extend(normalized)
                    status["skipped_count"] += not normalized
                except (ValueError, TypeError, KeyError, AttributeError):
                    status["rejected_count"] += 1
                    complete = False
            # An unexpected empty dump is not evidence that all programs closed.
            if not rows and any(p.platform == platform for p in previous.values()):
                complete = False
                status["error"] = "empty response; keeping last known data"
            status["count"] = len(batch)
            status["ok"] = complete
            if not complete:
                status["state"] = "partial" if batch else "failed"
                status.setdefault("error", "incomplete source response or rejected records")
        except Exception as exc:
            status.update(ok=False, state="failed", error=str(exc))
        if not status["ok"]:
            by_id = {p.id: p for p in batch}
            failed_sources = {s["source"] for s in status.get("sources", []) if not s.get("ok")}
            for old in previous.values():
                if old.platform != platform:
                    continue
                # Preserve authoritative data if its source failed, even if a lower-priority dump has a fallback.
                if old.id not in by_id or old.source in failed_sources:
                    cached = Program.from_dict(old.to_dict())
                    cached.stale = True
                    cached.added_assets = []
                    by_id[old.id] = cached
                    status["retained_count"] += 1
            batch = list(by_id.values())
        old_status = next((s for s in state.get("source_status", []) if s["platform"] == platform), {})
        status["last_success_at"] = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if status["ok"] else old_status.get("last_success_at")
        programs.extend(batch)
        source_status.append(status)

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
    pages_url = os.environ.get("PAGES_URL")
    history = append_history(state.get("history", []), diff, programs, previous, generated_at)
    pending = state.get("outbox", [])
    if send_telegram:
        pending = enqueue(pending, feeds, diff, source_status, pages_url)
    quality = {
        "generated_at": generated_at,
        "program_count": len(programs),
        "stale_count": sum(p.stale for p in programs),
        "rejected_count": sum(s.get("rejected_count", 0) for s in source_status),
        "skipped_count": sum(s.get("skipped_count", 0) for s in source_status),
        "incomplete_sources": sum(not s["ok"] for s in source_status),
        "pending_notifications": len(pending),
        "history_events": len(history),
    }
    save_snapshot(data_dir, programs, feeds, diff, source_status, generated_at, history=history, outbox=pending, quality=quality)
    snapshot = load_state(data_dir)
    telegram_sent, telegram_error = False, None
    if send_telegram:
        telegram_sent, telegram_error = flush(data_dir, snapshot, send_digest)
    quality = snapshot["quality"]
    atomic_json(data_dir / "quality.json", quality)
    publish_docs(docs_dir, data_dir, feeds, generated_at, pages_url)
    return {
        "count": len(programs),
        "feeds": feeds,
        "diff": diff,
        "source_status": source_status,
        "telegram_sent": telegram_sent,
        "telegram_error": telegram_error,
        "llm_used": llm_used,
        "quality": quality,
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
