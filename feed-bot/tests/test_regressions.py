import json
from datetime import datetime, timedelta, timezone

import httpx

from feed_bot.diff import diff_snapshot, stamp
from feed_bot.llm import _apply, copy_cached_llm
from feed_bot.normalize import normalize_self_host
from feed_bot.pipeline import run
from feed_bot.sources.arkadiyt import SourceError
from feed_bot.store import load_previous
from feed_bot.telegram import send_digest


def test_snapshot_sequence_and_source_recovery(tmp_path):
    rows = [{'name': 'A', 'handle': 'a', 'offers_bounties': True,
             'targets': {'in_scope': [{'asset_identifier': 'app.test', 'asset_type': 'URL'}]}}]
    failed = False
    def fetch(platform):
        if platform != 'hackerone':
            return []
        if failed:
            raise SourceError(platform, 'timeout')
        return rows
    start = datetime(2026, 9, 12, tzinfo=timezone.utc)
    def cycle(i):
        return run(data_dir=tmp_path/'data', docs_dir=tmp_path/'docs',
                   now=start+timedelta(hours=i), fetch_dump_fn=fetch,
                   fetch_hackenproof_fn=lambda: [], fetch_selfhost_fn=lambda: [],
                   send_telegram=False, enrich_llm=False)
    cycle(0)
    rows.append({**rows[0], 'name': 'B', 'handle': 'b'})
    second = cycle(1)
    assert [p['id'] for p in second['diff']['added']] == ['hackerone:b']
    third = cycle(2)
    assert third['diff']['added'] == []
    previous = load_previous(tmp_path/'data')
    assert previous['hackerone:b'].first_seen == '2026-09-12T01:00:00Z'
    failed = True
    for i in (3, 4):
        result = cycle(i)
        assert result['count'] == 2
        assert result['diff']['removed'] == []
        assert result['feeds']['recommended'] == []
        assert result['feeds']['new'] == []
        cached = load_previous(tmp_path/'data')
        assert cached['hackerone:b'].stale
        assert cached['hackerone:b'].last_seen == previous['hackerone:b'].last_seen
        public = json.loads((tmp_path/'docs/data/programs.min.json').read_text())
        assert all(p['stale'] for p in public['programs'])
    failed = False
    recovered = cycle(5)
    assert recovered['diff']['added'] == []
    assert recovered['feeds']['recommended']
    assert not load_previous(tmp_path/'data')['hackerone:b'].stale
    # A genuine successful removal still removes the program.
    rows.pop()
    assert cycle(6)['diff']['removed'][0]['id'] == 'hackerone:b'


def test_current_snapshot_preferred_with_backup_fallback(tmp_path):
    p = normalize_self_host({'name': 'Current', 'url': 'https://demo.test/security'})
    (tmp_path/'previous').mkdir()
    (tmp_path/'previous/programs.min.json').write_text(json.dumps({'programs': []}))
    current = tmp_path/'programs.min.json'
    current.write_text(json.dumps({'programs': [p.to_dict()]}))
    assert p.id in load_previous(tmp_path)
    current.unlink()
    assert load_previous(tmp_path) == {}


def test_removed_scope_is_reported_in_telegram(monkeypatch):
    raw = {'name': 'Demo', 'url': 'https://demo.test/security', 'domains': ['app.test', 'old.test']}
    old = normalize_self_host(raw)
    current = normalize_self_host({**raw, 'domains': ['app.test']})
    stamp([current], {old.id: old}, datetime.now(timezone.utc))
    diff = diff_snapshot([current], {old.id: old})
    assert diff['scope_changes'][0]['added'] == []
    assert diff['scope_changes'][0]['removed'] == ['old.test']
    requests = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, json):
            requests.append(json)
            return httpx.Response(200, request=httpx.Request('POST', url))
    monkeypatch.setattr('feed_bot.telegram.httpx.Client', Client)
    assert send_digest({}, diff, [], token='test', chat_id='test')
    assert '−old.test' in requests[0]['text']


def test_selfhost_preserves_scope_exclusions():
    p = normalize_self_host({'name': 'Demo', 'url': 'https://demo.test/security',
                             'domains': ['*.demo.test'],
                             'out_of_scope': ['admin.demo.test', 'Social engineering', '']})
    assert [a.identifier for a in p.out_of_scope] == ['admin.demo.test', 'Social engineering']
    assert all(not a.in_scope for a in p.out_of_scope)
    assert p.concrete_count == 0


def test_llm_cache_restores_enrichment_and_invalidates_changed_rewards():
    raw = {'name': 'Demo', 'url': 'https://demo.test/security'}
    old = normalize_self_host(raw)
    copy_cached_llm([old], {})  # Hash the raw inputs, as the pipeline does.
    _apply(old, {'name': 'Demo enriched', 'summary_vi': 'Bản dịch',
                 'min_bounty': 100, 'max_bounty': 5000, 'currency': 'USD',
                 'reward_types': ['cash'], 'contact': 'security@demo.test'})
    old.llm_status = 'ok'
    fresh = normalize_self_host(raw)
    copy_cached_llm([fresh], {old.id: old})
    assert fresh.llm_status == 'ok'
    assert (fresh.name, fresh.summary_vi, fresh.min_bounty, fresh.max_bounty, fresh.currency, fresh.contact) == (
        old.name, old.summary_vi, 100, 5000, 'USD', old.contact)
    for changes in ({'min_bounty': 200}, {'max_bounty': 9000}, {'currency': 'EUR'}, {'reward_types': ['swag']}):
        changed = normalize_self_host({**raw, **changes})
        copy_cached_llm([changed], {old.id: old})
        assert changed.llm_status != 'ok'
