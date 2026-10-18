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
