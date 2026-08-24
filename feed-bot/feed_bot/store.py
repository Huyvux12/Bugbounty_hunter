from __future__ import annotations

import json
import shutil
from pathlib import Path

from feed_bot.models import Program

REPO_ROOT = Path(__file__).resolve().parents[2]


def default_data_dir() -> Path:
    return REPO_ROOT / "data"


def default_docs_dir() -> Path:
    return REPO_ROOT / "docs"


def load_previous(data_dir: Path) -> dict[str, Program]:
    path = data_dir / "previous" / "programs.min.json"
    if not path.exists():
        path = data_dir / "programs.min.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("programs", payload) if isinstance(payload, dict) else payload
    programs = {}
    for row in rows:
        program = Program.from_dict(row)
        programs[program.id] = program
    return programs


def save_snapshot(
    data_dir: Path,
    programs: list[Program],
    feeds: dict,
    diff: dict,
    source_status: list[dict],
    generated_at: str,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    previous_dir = data_dir / "previous"
    previous_dir.mkdir(parents=True, exist_ok=True)
    feeds_dir = data_dir / "feeds"
    feeds_dir.mkdir(parents=True, exist_ok=True)

    current = data_dir / "programs.min.json"
    if current.exists():
        shutil.copyfile(current, previous_dir / "programs.min.json")

    payload = {
        "generated_at": generated_at,
        "count": len(programs),
        "source_status": source_status,
        "programs": [p.to_dict() for p in programs],
    }
    current.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (feeds_dir / "recommended.json").write_text(_dump(feeds["recommended"]), encoding="utf-8")
    (feeds_dir / "recommended_by_platform.json").write_text(
        json.dumps(feeds.get("recommended_by_platform") or {}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (feeds_dir / "easy.json").write_text(_dump(feeds["easy"]), encoding="utf-8")
    (feeds_dir / "new.json").write_text(_dump(feeds["new"]), encoding="utf-8")
    (data_dir / "diff.json").write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (data_dir / "source_status.json").write_text(
        json.dumps(source_status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


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
                "easy_score": program.get("easy_score"),
                "reasons": program.get("reasons"),
                "concrete_count": program.get("concrete_count"),
                "min_bounty": program.get("min_bounty"),
                "max_bounty": program.get("max_bounty"),
                "first_seen": program.get("first_seen"),
                "in_scope": program.get("in_scope") or [],
                "out_of_scope": program.get("out_of_scope") or [],
            }
        )
    (data_out / "programs.min.json").write_text(
        json.dumps({"generated_at": generated_at, "count": len(slim), "programs": slim}, ensure_ascii=False),
        encoding="utf-8",
    )
    feeds_out = dict(feeds)
    feeds_out["pages_base"] = pages_base
    (data_out / "feeds.json").write_text(json.dumps(feeds_out, ensure_ascii=False), encoding="utf-8")


def _dump(rows: list) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
