from feed_bot import cli


def test_public_source_failure_returns_nonzero_but_hackenproof_is_optional(monkeypatch, tmp_path, capsys):
    status = [
        {"platform": "hackenproof", "ok": False},
        {"platform": "hackerone", "ok": True},
    ]
    monkeypatch.setattr(cli, "run", lambda **kwargs: {
        "count": 1, "quality": {}, "source_status": status,
        "telegram_sent": False, "llm_used": 0,
    })
    assert cli.main(["--data-dir", str(tmp_path)]) == 0
    status[1]["ok"] = False
    assert cli.main(["--data-dir", str(tmp_path)]) == 1
