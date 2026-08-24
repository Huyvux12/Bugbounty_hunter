import json
from pathlib import Path

from feed_bot.normalize import normalize_many

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_hackerone_ios_not_url():
    programs = {p.handle: p for p in normalize_many("hackerone", load("hackerone.json"), "arkadiyt")}
    sb = programs["starbucks_japan"]
    kinds = {a.identifier: a.kind for a in sb.in_scope}
    assert kinds["www.starbucks.co.jp"] == "domain"
    assert kinds["https://login.starbucks.co.jp"] == "url"
    assert kinds["Starbucks Japan iOS"] == "mobile"
    assert sb.concrete_count == 2
    assert sb.offers_bounty is True


def test_other_platforms():
    bc = normalize_many("bugcrowd", load("bugcrowd.json"), "arkadiyt")[0]
    assert bc.id == "bugcrowd:tiny-startup-bb"
    assert bc.offers_bounty is True
    ig = normalize_many("intigriti", load("intigriti.json"), "arkadiyt")[0]
    assert ig.in_scope[0].kind == "domain"
    ywh = normalize_many("yeswehack", load("yeswehack.json"), "arkadiyt")[0]
    assert ywh.in_scope[0].kind == "url"
    fed = normalize_many("federacy", load("federacy.json"), "arkadiyt")[0]
    assert fed.concrete_count == 0
    assert fed.in_scope[0].kind == "wildcard"


def test_hackenproof_skips_archived():
    programs = normalize_many("hackenproof", load("hackenproof.json"), "hackenproof_mcp")
    assert [p.handle for p in programs] == ["hackenproof"]
    hp = programs[0]
    assert hp.status == "open"
    assert hp.offers_bounty is True
    assert hp.max_bounty == 1500
    assert hp.in_scope[0].identifier == "https://hackenproof.com"
    assert hp.in_scope[0].kind == "url"
    assert hp.out_of_scope[0].identifier == "blog.hackenproof.com"
