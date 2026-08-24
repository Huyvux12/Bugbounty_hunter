from __future__ import annotations

from datetime import datetime, timezone

from feed_bot.models import Program


def stamp(programs: list[Program], previous: dict[str, Program], now: datetime) -> list[Program]:
    iso = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for program in programs:
        old = previous.get(program.id)
        if old and old.first_seen:
            program.first_seen = old.first_seen
        else:
            program.first_seen = iso
        program.last_seen = iso
        if old:
            old_ids = {a.identifier for a in old.in_scope if a.identifier}
            new_ids = {a.identifier for a in program.in_scope if a.identifier}
            program.added_assets = sorted(new_ids - old_ids)
        else:
            program.added_assets = []
    return programs


def diff_snapshot(programs: list[Program], previous: dict[str, Program]) -> dict:
    current_ids = {p.id for p in programs}
    prev_ids = set(previous)
    added = [p for p in programs if p.id not in prev_ids]
    removed = [previous[i] for i in sorted(prev_ids - current_ids)]
    scope_changes = []
    for program in programs:
        old = previous.get(program.id)
        if not old:
            continue
        if program.added_assets:
            old_ids = {a.identifier for a in old.in_scope if a.identifier}
            new_ids = {a.identifier for a in program.in_scope if a.identifier}
            scope_changes.append(
                {
                    "id": program.id,
                    "name": program.name,
                    "platform": program.platform,
                    "url": program.url,
                    "added": program.added_assets[:8],
                    "removed": sorted(old_ids - new_ids)[:8],
                }
            )
    return {
        "added": [{"id": p.id, "name": p.name, "platform": p.platform, "url": p.url} for p in added],
        "removed": [{"id": p.id, "name": p.name, "platform": p.platform} for p in removed],
        "scope_changes": scope_changes,
    }


def has_material_diff(diff: dict) -> bool:
    return bool(diff.get("added") or diff.get("scope_changes"))
