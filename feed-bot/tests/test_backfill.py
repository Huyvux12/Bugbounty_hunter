from datetime import datetime, timedelta, timezone

from feed_bot.pipeline import run
from feed_bot.sources.result import FetchBatch


def test_first_uncapped_run_does_not_announce_old_programs(tmp_path):
    data = tmp_path / "data"
    docs = tmp_path / "docs"
    old = {"name": "Old", "url": "https://old.test/security"}
    expanded = {"name": "Previously hidden", "url": "https://hidden.test/security"}
    new = {"name": "Actually new", "url": "https://new.test/security"}
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)

    def execute(rows, when, capped=False):
        return run(data_dir=data, docs_dir=docs, now=when,
                   fetch_dump_fn=lambda platform: [], fetch_hackenproof_fn=lambda: [],
                   fetch_selfhost_fn=lambda: FetchBatch(rows, sources=[
                       {"source": "limit", "ok": True, "truncated": 1}] if capped else []),
                   send_telegram=False, enrich_llm=False)

    execute([old], now, capped=True)
    backfill = execute([old, expanded], now + timedelta(hours=6))
    assert backfill["diff"]["added"] == []
    assert backfill["feeds"]["new"] == []
    assert backfill["quality"]["llm"]["used_this_run"] == 0

    actual = execute([old, expanded, new], now + timedelta(hours=12))
    assert [item["name"] for item in actual["diff"]["added"]] == ["Actually new"]
