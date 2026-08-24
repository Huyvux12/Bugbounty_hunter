from datetime import datetime, timedelta, timezone

from feed_bot.diff import diff_snapshot, stamp
from feed_bot.models import Asset, Program
from feed_bot.rank import build_feeds, score_program


def _prog(**kwargs):
    base = dict(
        id="hackerone:demo",
        platform="hackerone",
        handle="demo",
        name="Demo",
        url="https://hackerone.com/demo",
        offers_bounty=True,
        status="open",
        source="arkadiyt",
        visibility="public",
        in_scope=[Asset("https://app.demo.test", "URL", True, "url")],
        concrete_count=1,
    )
    base.update(kwargs)
    return Program(**base)


def test_wildcard_only_not_recommended():
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    wild = _prog(
        id="hackerone:google",
        handle="google",
        name="Google",
        in_scope=[Asset("*.google.com", "WILDCARD", True, "wildcard")],
        concrete_count=0,
        first_seen="2020-01-01T00:00:00Z",
    )
    easy = _prog(
        id="bugcrowd:tiny-startup-bb",
        platform="bugcrowd",
        handle="tiny-startup-bb",
        name="Tiny Startup BB",
        first_seen=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    feeds = build_feeds([wild, easy], now, has_history=False)
    ids = [c["id"] for c in feeds["recommended"]]
    assert "bugcrowd:tiny-startup-bb" in ids
    assert "hackerone:google" not in ids


def test_new_and_scope_diff():
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    old = _prog(first_seen="2026-01-01T00:00:00Z")
    incoming = _prog(
        in_scope=[
            Asset("https://app.demo.test", "URL", True, "url"),
            Asset("https://api.demo.test", "URL", True, "url"),
        ],
        concrete_count=2,
    )
    stamped = stamp([incoming], {old.id: old}, now)[0]
    assert stamped.added_assets == ["https://api.demo.test"]
    assert stamped.first_seen == "2026-01-01T00:00:00Z"
    diff = diff_snapshot([stamped], {old.id: old})
    assert diff["scope_changes"][0]["added"] == ["https://api.demo.test"]

    brand_new = _prog(id="hackerone:fresh", handle="fresh", name="Fresh")
    stamped_new = stamp([brand_new], {}, now)[0]
    feeds = build_feeds([stamped_new], now, has_history=True)
    assert feeds["new"][0]["id"] == "hackerone:fresh"
    baseline = build_feeds([stamped_new], now, has_history=False)
    assert baseline["new"] == []


def test_recommended_mixes_platforms():
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    programs = []
    for i in range(8):
        programs.append(
            _prog(
                id=f"hackerone:h{i}",
                handle=f"h{i}",
                name=f"H{i}",
                platform="hackerone",
            )
        )
    programs.append(
        _prog(
            id="bugcrowd:tiny-startup-bb",
            platform="bugcrowd",
            handle="tiny-startup-bb",
            name="Tiny Startup BB",
        )
    )
    programs.append(
        _prog(
            id="intigriti:aikido",
            platform="intigriti",
            handle="aikido",
            name="Aikido",
        )
    )
    feeds = build_feeds(programs, now, has_history=False)
    platforms = {c["platform"] for c in feeds["recommended"]}
    assert "hackerone" in platforms
    assert "bugcrowd" in platforms
    assert "intigriti" in platforms
    assert feeds["recommended_by_platform"]["bugcrowd"][0]["id"] == "bugcrowd:tiny-startup-bb"


def test_score_clamped():
    now = datetime.now(timezone.utc)
    p = _prog(status="paused", first_seen=(now - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    score_program(p, now)
    assert 0 <= p.easy_score <= 100
