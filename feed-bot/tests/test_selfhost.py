from feed_bot.llm import Pace, _apply, chat_url, content_hash, copy_cached_llm, decode_chat_response, max_per_run_from_env, rpm_from_env
from feed_bot.models import Program
from feed_bot.normalize import normalize_many
from feed_bot.pipeline import run
from feed_bot.rewards import infer_reward_types
from feed_bot.sources.selfhost import _from_diodb, _from_lissy, _from_pd, _is_platform, _merge, fetch_selfhost
from feed_bot.sources.result import FetchBatch
from datetime import datetime, timezone
from pathlib import Path
import json

FIXTURES = Path(__file__).parent / "fixtures"


def test_platform_urls_filtered():
    assert _is_platform("https://hackerone.com/airbnb")
    assert _is_platform("https://bugcrowd.com/acorns")
    assert not _is_platform("https://www.alwaysdata.com/en/bug-bounty/")


def test_untrusted_policy_url_is_rejected():
    assert normalize_many("self-host", [{"name": "Bad", "url": "javascript:alert(1)"}], "selfhost_dump") == []


def test_diodb_skips_platform_and_dead():
    rows = _from_diodb(
        [
            {"program_name": "Airbnb", "policy_url": "https://hackerone.com/airbnb", "offers_bounty": "yes"},
            {"program_name": "Dead", "policy_url": "https://example.com/vdp", "policy_url_status": "dead"},
            {"program_name": "AlwaysData", "policy_url": "https://www.alwaysdata.com/en/bug-bounty/", "offers_bounty": "yes", "offers_swag": True},
        ]
    )
    assert [r["name"] for r in rows] == ["AlwaysData"]


def test_lissy_yaml_and_rewards():
    yaml_text = """
companies:
- company: Ably
  url: https://ably.com/disclosure
  contact: mailto:disclosure@ably.com
  rewards:
  - '*bounty'
  - '*recognition'
  min_payout: 150
  max_payout: 5000
  currency: USD
  domains:
  - ably.com
"""
    rows = _from_lissy(yaml_text)
    assert rows[0]["name"] == "Ably"
    types = infer_reward_types(rows[0])
    assert "cash" in types
    assert "hall_of_fame" in types
    programs = normalize_many("self-host", rows, "selfhost_dump")
    assert programs[0].platform == "self-host"
    assert programs[0].id.startswith("self-host:")
    assert programs[0].min_bounty == 150
    assert "domain" in programs[0].scope_kinds or programs[0].concrete_count >= 1


def test_pd_skips_hackerone():
    rows = _from_pd({"programs": [{"name": "X", "url": "https://hackerone.com/x", "bounty": True, "domains": ["x.com"]}]})
    assert rows == []


def test_merge_prefers_lissy():
    merged = _merge(
        [
            {"name": "A", "url": "https://ably.com/disclosure", "source_dump": "diodb"},
            {"name": "Ably", "url": "https://ably.com/disclosure", "source_dump": "lissy93", "domains": ["ably.com"]},
        ]
    )
    assert merged[0]["name"] == "Ably"
    assert merged[0]["domains"] == ["ably.com"]


def test_shared_host_policies_remain_distinct():
    rows = _merge([
        {"name": "One", "url": "https://github.com/one/app/security/policy", "source_dump": "diodb"},
        {"name": "Two", "url": "https://github.com/two/app/security/policy", "source_dump": "diodb"},
    ])
    programs = normalize_many("self-host", rows, "selfhost_dump")
    assert len({p.id for p in programs}) == 2


def test_selfhost_does_not_drop_programs_after_500():
    class Response:
        def __init__(self, payload, text="companies: []"):
            self.payload = payload
            self.text = text
        def raise_for_status(self): pass
        def json(self): return self.payload
    class Client:
        def get(self, url):
            if "Lissy93" in url:
                return Response([], "companies: [{company: Lissy, url: 'https://lissy.test/security'}]")
            if "projectdiscovery" in url:
                return Response({"programs": [{"name": "PD", "url": "https://pd.test/security"}]})
            if "disclose" in url:
                return Response([{"program_name": f"Company {i}",
                                  "policy_url": f"https://company{i}.test/security"}
                                 for i in range(501)])
            return Response([])
    batch = fetch_selfhost(Client())
    assert len(batch) == 503
    assert batch.complete
    assert next(s for s in batch.sources if s["source"] == "merge")["count"] == 503


def test_empty_subsource_marks_batch_incomplete():
    class Client:
        def get(self, url):
            import httpx
            if "Lissy93" in url:
                return httpx.Response(200, text="companies: []")
            if "projectdiscovery" in url:
                return httpx.Response(200, json={"programs": [
                    {"name": "PD", "url": "https://pd.test/security"}]})
            return httpx.Response(200, json=[
                {"program_name": "DIODB", "policy_url": "https://diodb.test/security"}])
    batch = fetch_selfhost(Client())
    assert not batch.complete
    assert any(s["source"] == "lissy93" and not s["ok"] for s in batch.sources)


def test_pipeline_selfhost(tmp_path):
    rows = json.loads((FIXTURES / "selfhost.json").read_text(encoding="utf-8"))
    result = run(
        data_dir=tmp_path / "data",
        docs_dir=tmp_path / "docs",
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        fetch_dump_fn=lambda platform: [],
        fetch_hackenproof_fn=lambda: [],
        fetch_selfhost_fn=lambda: rows,
        send_telegram=False,
        enrich_llm=False,
    )
    assert result["count"] == 1
    via = {s["platform"]: s for s in result["source_status"]}
    assert via["self-host"]["ok"] is True
    published = json.loads((tmp_path / "docs" / "data" / "programs.min.json").read_text(encoding="utf-8"))
    item = published["programs"][0]
    assert item["platform"] == "self-host"
    assert "cash" in item["reward_types"]


def test_pace_15_rpm(monkeypatch):
    monkeypatch.setenv("LLM_RPM", "15")
    assert rpm_from_env() == 15
    sleeps: list[float] = []
    now = [0.0]

    def clock() -> float:
        return now[0]

    def sleeper(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    pace = Pace(15, sleeper=sleeper, clock=clock)
    pace.wait()
    assert sleeps == []
    now[0] += 0.5
    pace.wait()
    assert len(sleeps) == 1
    assert abs(sleeps[0] - 3.5) < 0.01


def test_llm_run_limit_is_configurable(monkeypatch):
    monkeypatch.setenv("LLM_MAX_PER_RUN", "240")
    assert max_per_run_from_env() == 240
    monkeypatch.setenv("LLM_MAX_PER_RUN", "9999")
    assert max_per_run_from_env() == 300


def test_chat_url_and_sse_decode():
    assert chat_url("https://example.test/v1") == "https://example.test/v1/chat/completions"
    assert chat_url("https://example.test") == "https://example.test/v1/chat/completions"
    class Fake:
        headers = {"content-type": "text/event-stream"}
        text = (
            'data: {"choices":[{"delta":{"content":"{\\"summary_vi\\":\\""}}]}\n'
            'data: {"choices":[{"delta":{"content":"xin chào\\"}"}}]}\n'
            "data: [DONE]\n"
        )
        def json(self):
            raise AssertionError("json() should not run for SSE")
    payload = decode_chat_response(Fake())
    assert payload["choices"][0]["message"]["content"] == '{"summary_vi":"xin chào"}'


def test_llm_apply_and_cache():
    program = normalize_many(
        "self-host",
        [{"name": "Demo Co", "url": "https://demo.test/security", "offers_bounty": "yes", "source_dump": "diodb"}],
        "selfhost_dump",
    )[0]
    _apply(program, {"summary_vi": "Chương trình trả tiền.", "reward_types": ["cash", "swag"], "contact": "security@demo.test"})
    assert program.summary_vi.startswith("Chương trình")
    assert "swag" in program.reward_types
    program.llm_status = "ok"
    program.content_hash = content_hash(program)
    clone = Program.from_dict(program.to_dict())
    clone.llm_status = None
    clone.summary_vi = None
    copy_cached_llm([clone], {program.id: program})
    assert clone.summary_vi == program.summary_vi
    assert clone.llm_status == "ok"
