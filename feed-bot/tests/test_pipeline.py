import json
from datetime import datetime, timezone
from pathlib import Path

from feed_bot.pipeline import run
from feed_bot.sources.arkadiyt import SourceError

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_pipeline_arkadiyt_and_hackenproof(tmp_path, monkeypatch):
    dumps = {
        "hackerone": _load("hackerone.json"),
        "bugcrowd": _load("bugcrowd.json"),
        "intigriti": _load("intigriti.json"),
        "yeswehack": _load("yeswehack.json"),
        "federacy": _load("federacy.json"),
    }

    def fetch_dump(platform: str):
        return dumps[platform]

    result = run(
        data_dir=tmp_path / "data",
        docs_dir=tmp_path / "docs",
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        fetch_dump_fn=fetch_dump,
        fetch_hackenproof_fn=lambda: _load("hackenproof.json"),
        send_telegram=False,
    )
    assert result["count"] >= 6
    via = {s["platform"]: s["via"] for s in result["source_status"] if s["ok"]}
    assert via["hackerone"] == "arkadiyt"
    assert via["hackenproof"] == "mcp"
    feeds = json.loads((tmp_path / "docs" / "data" / "feeds.json").read_text(encoding="utf-8"))
    rec_ids = [c["id"] for c in feeds["recommended"]]
    assert "hackerone:google" not in rec_ids
    assert any("starbucks" in i or "tiny" in i or "aikido" in i or "hackenproof" in i for i in rec_ids)


def test_dump_fail_does_not_stop_other_sources(tmp_path):
    def fetch_dump(platform: str):
        if platform == "hackerone":
            raise SourceError("hackerone", "timeout")
        return _load(f"{platform}.json") if platform != "federacy" else _load("federacy.json")

    result = run(
        data_dir=tmp_path / "data",
        docs_dir=tmp_path / "docs",
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        fetch_dump_fn=fetch_dump,
        fetch_hackenproof_fn=lambda: (_ for _ in ()).throw(SourceError("hackenproof", "HACKENPROOF_API_KEY missing")),
        send_telegram=False,
    )
    status = {s["platform"]: s for s in result["source_status"]}
    assert status["hackerone"]["ok"] is False
    assert status["bugcrowd"]["ok"] is True
    assert status["hackenproof"]["ok"] is False
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
        fetch_hackenproof_fn=lambda: [],
        send_telegram=True,
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
        fetch_hackenproof_fn=lambda: [],
        send_telegram=True,
    )
    assert result["telegram_sent"] is False
    assert "401" in (result.get("telegram_error") or "")
    assert (tmp_path / "data" / "programs.min.json").exists()
