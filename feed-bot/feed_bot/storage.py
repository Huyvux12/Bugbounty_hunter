"""Atomic JSON writes: serialize first, fsync a sibling file, then replace."""
import json
import os
import tempfile
from pathlib import Path


def atomic_json(path: Path, payload) -> None:
    content = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".feed-", delete=False) as file:
            temp = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def read_snapshot(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f"Invalid JSON number {v}")))
    if isinstance(payload, list):
        payload = {"programs": payload}
    if not isinstance(payload, dict) or not isinstance(payload.get("programs"), list):
        raise ValueError("Invalid snapshot structure")
    from feed_bot.models import Program
    ids = []
    for row in payload["programs"]:
        program = Program.from_dict(row)
        ids.append(program.id)
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate program IDs in snapshot")
    for key in ("history", "outbox"):
        if not isinstance(payload.get(key, []), list):
            raise ValueError(f"Invalid snapshot {key}")
    return payload


def load_state(data_dir: Path) -> dict:
    failures = []
    for path in (data_dir / "programs.min.json", data_dir / "previous/programs.min.json"):
        if not path.exists():
            continue
        try:
            return read_snapshot(path)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            failures.append(f"{path.name}: {exc}")
    if failures:
        raise ValueError("No valid snapshot or backup: " + "; ".join(failures))
    return {"programs": [], "history": [], "outbox": []}
