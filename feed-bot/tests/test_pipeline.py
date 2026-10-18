import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from feed_bot.models import Program
from feed_bot.pipeline import run
from feed_bot.sources.arkadiyt import SourceError
from feed_bot.storage import atomic_json, load_state

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("retired", ["federacy", "hackenproof"])
def test_retired_source_is_removed_without_false_closure(tmp_path, retired):
    data = tmp_path / "data"
    docs = tmp_path / "docs"
    legacy = Program(id=f"{retired}:old", platform=retired, handle="old",
                     name="Old program", url="https://old.test", offers_bounty=True,
                     status="open", source="legacy", visibility="public", stale=True)
    history = [{"event_id": "original-event", "kind": "added", "id": legacy.id}]
    atomic_json(data / "programs.min.json", {
        "programs": [legacy.to_dict()], "history": history,
        "source_status": [{"platform": retired, "ok": False}],
    })
    requested = []

    def fetch(platform):
        requested.append(platform)
        return _load(f"{platform}.json")

    for _ in range(2):
        result = run(data_dir=data, docs_dir=docs, fetch_dump_fn=fetch,
                     fetch_selfhost_fn=lambda: [], send_telegram=False, enrich_llm=False)
        saved = load_state(data)
        assert all(p["platform"] not in {"federacy", "hackenproof"} for p in saved["programs"])
        assert all(s["platform"] not in {"federacy", "hackenproof"} for s in result["source_status"])
        assert not result["diff"]["removed"]
        assert history[0] in saved["history"]
        assert result["quality"]["incomplete_sources"] == 0
        public = json.loads((docs / "data" / "programs.min.json").read_text())
        assert all(p["platform"] not in {"federacy", "hackenproof"} for p in public["programs"])
    assert set(requested) == {"hackerone", "bugcrowd", "intigriti", "yeswehack"}


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_pipeline_public_dumps(tmp_path, monkeypatch):
    dumps = {
        "hackerone": _load("hackerone.json"),
        "bugcrowd": _load("bugcrowd.json"),
        "intigriti": _load("intigriti.json"),
        "yeswehack": _load("yeswehack.json"),
    }

    def fetch_dump(platform: str):
        return dumps[platform]

    result = run(
        data_dir=tmp_path / "data",
        docs_dir=tmp_path / "docs",
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        fetch_dump_fn=fetch_dump,
        fetch_selfhost_fn=lambda: [],
        send_telegram=False,
        enrich_llm=False,
    )
    assert result["count"] >= 4
    via = {s["platform"]: s["via"] for s in result["source_status"] if s["ok"]}
    assert via["hackerone"] == "arkadiyt"
    feeds = json.loads((tmp_path / "docs" / "data" / "feeds.json").read_text(encoding="utf-8"))
    rec_ids = [c["id"] for c in feeds["recommended"]]
    assert "hackerone:google" not in rec_ids
    assert any("starbucks" in i or "tiny" in i or "aikido" in i for i in rec_ids)


def test_dump_fail_does_not_stop_other_sources(tmp_path):
    def fetch_dump(platform: str):
        if platform == "hackerone":
            raise SourceError("hackerone", "timeout")
        return _load(f"{platform}.json")

    result = run(
        data_dir=tmp_path / "data",
        docs_dir=tmp_path / "docs",
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        fetch_dump_fn=fetch_dump,
        fetch_selfhost_fn=lambda: [],
        send_telegram=False,
        enrich_llm=False,
    )
    status = {s["platform"]: s for s in result["source_status"]}
    assert status["hackerone"]["ok"] is False
    assert status["bugcrowd"]["ok"] is True
    assert result["count"] > 0


def test_missing_telegram_does_not_fail(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    def fetch_dump(platform: str):
        if platform == "hackerone":
            return _load("hackerone.json")
        return []

    result = run(
        data_dir=tmp_path / "data",
        docs_dir=tmp_path / "docs",
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        fetch_dump_fn=fetch_dump,
        fetch_selfhost_fn=lambda: [],
        send_telegram=True,
        enrich_llm=False,
    )
    assert result["telegram_sent"] is False
    assert result.get("telegram_error") is None


def test_telegram_http_error_still_saves_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")

    def boom(*_args, **_kwargs):
        raise RuntimeError("telegram 401")

    monkeypatch.setattr("feed_bot.pipeline.send_digest", boom)

    def fetch_dump(platform: str):
        if platform == "hackerone":
            return _load("hackerone.json")
        return []

    result = run(
        data_dir=tmp_path / "data",
        docs_dir=tmp_path / "docs",
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        fetch_dump_fn=fetch_dump,
        fetch_selfhost_fn=lambda: [],
        send_telegram=True,
        enrich_llm=False,
    )
    assert result["telegram_sent"] is False
    assert result["telegram_error"] == "RuntimeError"
    assert result["quality"]["pending_notifications"] == 1
    assert (tmp_path / "data" / "programs.min.json").exists()
