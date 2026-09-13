from __future__ import annotations

import json
from feed_bot.storage import atomic_json, load_state, read_snapshot
from pathlib import Path

from feed_bot.models import Program

REPO_ROOT = Path(__file__).resolve().parents[2]


def default_data_dir() -> Path:
    return REPO_ROOT / "data"


def default_docs_dir() -> Path:
    return REPO_ROOT / "docs"


def load_previous(data_dir: Path) -> dict[str, Program]:
    rows = load_state(data_dir)["programs"]
    return {row["id"]: Program.from_dict(row) for row in rows}


def save_snapshot(
    data_dir: Path,
    programs: list[Program],
    feeds: dict,
    diff: dict,
    source_status: list[dict],
    generated_at: str,
    history: list | None = None,
    outbox: list | None = None,
    quality: dict | None = None,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    previous_dir = data_dir / "previous"
    previous_dir.mkdir(parents=True, exist_ok=True)
    feeds_dir = data_dir / "feeds"
    feeds_dir.mkdir(parents=True, exist_ok=True)

    current = data_dir / "programs.min.json"
    old = load_state(data_dir)
    payload = {
        "generated_at": generated_at,
        "count": len(programs),
        "source_status": source_status,
        "programs": [p.to_dict() for p in programs],
        "history": history if history is not None else old.get("history", []),
        "outbox": outbox if outbox is not None else old.get("outbox", []),
        "quality": quality or {},
    }
    # Check serialization before rotating the last known good backup.
    json.dumps(payload, allow_nan=False)
    if current.exists():
        try:
            valid = read_snapshot(current)
        except (ValueError, TypeError, KeyError, OSError):
            pass  # Never overwrite a good backup with a corrupt current file.
        else:
            atomic_json(previous_dir / "programs.min.json", valid)
    atomic_json(current, payload)
    for name in ("recommended", "recommended_by_platform", "easy", "new"):
        atomic_json(feeds_dir / f"{name}.json", feeds.get(name, {} if name.endswith("platform") else []))
    atomic_json(data_dir / "diff.json", diff)
    atomic_json(data_dir / "source_status.json", source_status)
    atomic_json(data_dir / "quality.json", quality or {})


def publish_docs(docs_dir: Path, data_dir: Path, feeds: dict, generated_at: str, pages_base: str | None) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    data_out = docs_dir / "data"
    data_out.mkdir(parents=True, exist_ok=True)
    public_path = data_dir / "programs.min.json"
    payload = json.loads(public_path.read_text(encoding="utf-8"))
    public_programs = [p for p in payload.get("programs", []) if p.get("visibility") != "access-scoped"]
    slim = []
    for program in public_programs:
        slim.append(
            {
                "id": program["id"],
                "platform": program["platform"],
                "handle": program.get("handle"),
                "name": program["name"],
                "url": program["url"],
                "offers_bounty": program.get("offers_bounty"),
                "status": program.get("status"),
                "stale": program.get("stale", False),
                "last_seen": program.get("last_seen"),
                "easy_score": program.get("easy_score"),
                "reasons": program.get("reasons"),
                "concrete_count": program.get("concrete_count"),
                "min_bounty": program.get("min_bounty"),
                "max_bounty": program.get("max_bounty"),
                "currency": program.get("currency"),
                "first_seen": program.get("first_seen"),
                "in_scope": program.get("in_scope") or [],
                "out_of_scope": program.get("out_of_scope") or [],
                "reward_types": program.get("reward_types") or [],
                "scope_kinds": program.get("scope_kinds") or [],
                "summary_vi": program.get("summary_vi"),
                "policy_url": program.get("policy_url"),
                "contact": program.get("contact"),
            }
        )
    atomic_json(data_out / "programs.min.json", {"generated_at": generated_at, "count": len(slim), "programs": slim})
    feeds_out = dict(feeds)
    feeds_out["pages_base"] = pages_base
    feeds_out["quality"] = payload.get("quality", {})
    feeds_out["source_status"] = payload.get("source_status", [])
    public_ids = {p["id"] for p in public_programs}
    for key in ("recommended", "easy", "new"):
        feeds_out[key] = [p for p in feeds_out.get(key, []) if p["id"] in public_ids]
    feeds_out["recommended_by_platform"] = {
        key: [p for p in rows if p["id"] in public_ids]
        for key, rows in feeds_out.get("recommended_by_platform", {}).items()
    }
    atomic_json(data_out / "feeds.json", feeds_out)
    atomic_json(data_out / "history.json", {
        "generated_at": generated_at,
        "events": [e for e in payload.get("history", []) if e.get("visibility", "public") == "public"],
    })
