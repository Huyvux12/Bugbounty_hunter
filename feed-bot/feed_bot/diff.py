from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from feed_bot.models import Program


def stamp(programs: list[Program], previous: dict[str, Program], now: datetime) -> list[Program]:
    iso = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for program in programs:
        if program.stale:
            continue
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
    program_changes = []
    for program in programs:
        if program.stale:
            continue
        old = previous.get(program.id)
        if not old:
            continue
        scopes = {}
        for field in ("in_scope", "out_of_scope"):
            before = {a.identifier: a.to_dict() for a in getattr(old, field) if a.identifier}
            after = {a.identifier: a.to_dict() for a in getattr(program, field) if a.identifier}
            change = {
                "added": sorted(after.keys() - before.keys()),
                "removed": sorted(before.keys() - after.keys()),
                "updated": [{"identifier": key, "before": before[key], "after": after[key]}
                            for key in sorted(before.keys() & after.keys()) if before[key] != after[key]],
            }
            if any(change.values()):
                scopes[field] = change
        if scopes:
            inside = scopes.get("in_scope", {})
            scope_changes.append({
                "id": program.id, "name": program.name, "platform": program.platform, "url": program.url,
                "added": inside.get("added", []), "removed": inside.get("removed", []), "scopes": scopes,
            })
        fields = {}
        for field in ("status", "offers_bounty", "min_bounty", "max_bounty", "currency", "reward_types", "policy_url", "contact"):
            before, after = getattr(old, field), getattr(program, field)
            if before != after:
                fields[field] = {"before": before, "after": after}
        if fields:
            program_changes.append({"id": program.id, "name": program.name, "platform": program.platform, "url": program.url, "fields": fields})
    return {
        "added": [{"id": p.id, "name": p.name, "platform": p.platform, "url": p.url} for p in added],
        "removed": [{"id": p.id, "name": p.name, "platform": p.platform} for p in removed],
        "scope_changes": scope_changes,
        "program_changes": program_changes,
    }


def has_material_diff(diff: dict) -> bool:
    return any(diff.get(key) for key in ("added", "removed", "scope_changes", "program_changes"))


def append_history(history: list, diff: dict, programs: list[Program], previous: dict[str, Program], generated_at: str) -> list:
    result = list(history)
    known = {e["event_id"] for e in history}
    by_id = {**previous, **{p.id: p for p in programs}}
    for kind in ("added", "removed", "scope_changes", "program_changes"):
        for change in diff.get(kind, []):
            raw = json.dumps([generated_at, kind, change], ensure_ascii=False, sort_keys=True, allow_nan=False)
            event_id = hashlib.sha256(raw.encode()).hexdigest()
            if event_id in known:
                continue
            result.append({"event_id": event_id, "at": generated_at, "kind": kind, **change,
                           "visibility": by_id[change["id"]].visibility})
            known.add(event_id)
    return result
