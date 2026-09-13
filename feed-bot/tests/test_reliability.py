import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from feed_bot.classify import classify_kind
from feed_bot.diff import append_history, diff_snapshot, stamp
from feed_bot.llm import _apply
from feed_bot.models import Program
from feed_bot.normalize import normalize_self_host
from feed_bot.pipeline import run
from feed_bot.rank import build_feeds
from feed_bot.sources.hackenproof import fetch_hackenproof
from feed_bot.sources.selfhost import fetch_selfhost, _from_lissy, LISSY_URL, PD_URL
from feed_bot.storage import atomic_json, load_state
from feed_bot.store import load_previous, save_snapshot
from feed_bot.telegram import send_digest

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


def program(**changes):
    raw = {'name': 'Demo', 'url': 'https://demo.test/security', 'domains': ['app.demo.test'],
           'offers_bounty': True, 'min_bounty': 10, 'max_bounty': 100, 'currency': 'USD'}
    raw.update(changes)
    return normalize_self_host(raw)


def runner(tmp_path, fetch=lambda _: [], **kwargs):
    return run(data_dir=tmp_path/'data', docs_dir=tmp_path/'docs', fetch_dump_fn=fetch,
               fetch_hackenproof_fn=kwargs.pop('hp', lambda: []),
               fetch_selfhost_fn=kwargs.pop('sh', lambda: []), enrich_llm=False,
               send_telegram=kwargs.pop('send', False), **kwargs)


def test_partial_dump_retains_missing_and_authoritative_records(tmp_path):
    partial = [False]
    def respond(request):
        if str(request.url) == LISSY_URL:
            if partial[0]:
                return httpx.Response(503)
            return httpx.Response(200, text='companies:\n- company: Official A\n  url: https://a.test/security\n  domains: [app.a.test]\n')
        if str(request.url) == PD_URL:
            return httpx.Response(200, json={'programs': [{'name': 'Fallback A', 'url': 'https://a.test/security', 'domains': ['other.a.test']}, {'name': 'B', 'url': 'https://b.test/security'}]})
        return httpx.Response(200, json=[])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        runner(tmp_path, sh=lambda: fetch_selfhost(client), now=NOW)
        partial[0] = True
        result = runner(tmp_path, sh=lambda: fetch_selfhost(client), now=NOW+timedelta(hours=6))
    saved = load_previous(tmp_path/'data')
    assert saved['self-host:a-test'].name == 'Official A'
    assert saved['self-host:a-test'].stale
    assert not saved['self-host:b-test'].stale
    status = result['source_status'][-1]
    assert status['state'] == 'partial' and status['retained_count'] == 1
    assert status['last_success_at'] == '2026-09-12T00:00:00Z'
    assert not result['diff']['removed']


def test_hackenproof_all_error_responses_are_incomplete():
    class MCP:
        def call_tool(self, name, args):
            return {'companies': []} if name == 'list_companies' else {'error': 'upstream unavailable'}
    batch = fetch_hackenproof(api_key='fake', client_factory=MCP, slugs=['a', 'b'], discover=False)
    assert batch == [] and not batch.complete
    assert len(batch.sources) == 2 and all(not s['ok'] for s in batch.sources)


def test_hackenproof_not_found_slug_keeps_batch_complete():
    class MCP:
        def call_tool(self, name, args):
            if name == 'list_companies':
                return {'companies': []}
            if args.get('program') == 'gone':
                return {'error': '404'}
            return {'title': 'Live', 'state': 'open', 'program': args.get('program')}
    batch = fetch_hackenproof(api_key='fake', client_factory=MCP, slugs=['live', 'gone'], discover=False)
    assert [row['slug'] for row in batch] == ['live']
    assert batch.complete
    gone = next(s for s in batch.sources if s['source'] == 'gone')
    assert gone['ok'] is True and gone.get('gone') is True


def test_selfhost_cap_is_complete_and_drops_overflow(tmp_path, monkeypatch):
    yaml_text = (
        'companies:\n'
        '- company: Cash Co\n'
        '  url: https://cash.test/security\n'
        '  rewards: ["*bounty"]\n'
        '- company: Other Co\n'
        '  url: https://other.test/security\n'
    )
    def respond(request):
        url = str(request.url)
        if url == LISSY_URL:
            return httpx.Response(200, text=yaml_text)
        if url == PD_URL:
            return httpx.Response(200, json={'programs': []})
        return httpx.Response(200, json=[])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr('feed_bot.sources.selfhost.MAX_PROGRAMS', 10)
        runner(tmp_path, sh=lambda: fetch_selfhost(client), now=NOW)
        monkeypatch.setattr('feed_bot.sources.selfhost.MAX_PROGRAMS', 1)
        result = runner(tmp_path, sh=lambda: fetch_selfhost(client), now=NOW + timedelta(hours=6))
    saved = load_previous(tmp_path / 'data')
    status = next(s for s in result['source_status'] if s['platform'] == 'self-host')
    assert status['ok'] is True and status['state'] == 'complete'
    assert 'self-host:cash-test' in saved
    assert 'self-host:other-test' not in saved
    assert not saved['self-host:cash-test'].stale
    limit = next(s for s in status.get('sources', []) if s.get('source') == 'limit')
    assert limit['ok'] is True and limit['truncated'] == 1


def test_empty_and_malformed_dump_does_not_remove_last_good(tmp_path):
    row = {'handle': 'a', 'name': 'A'}
    runner(tmp_path, fetch=lambda p: [row] if p == 'hackerone' else [])
    result = runner(tmp_path)
    assert result['quality']['stale_count'] == 1
    assert result['diff']['removed'] == []
    result = runner(tmp_path, fetch=lambda p: [None, {**row, 'targets': 123}] if p == 'hackerone' else [])
    assert result['quality']['rejected_count'] == 2
    assert result['quality']['stale_count'] == 1


@pytest.mark.parametrize('status', ['archived', 'retired', 'unknown', 'inactive'])
def test_non_open_status_never_recommended(status):
    p = program(status=status)
    assert p.status != 'open'
    assert not build_feeds([p], NOW)['recommended']


def test_yaml_lists_aliases_and_multiline_description():
    rows = _from_lissy('''domains: &assets [app.demo.test]
companies:
- company: Demo
  url: https://demo.test/security
  domains: *assets
  out_of_scope: [admin.demo.test]
  description: |
    Report vulnerabilities.
    Contact: security team.
''')
    p = normalize_self_host(rows[0])
    assert p.concrete_count == 1
    assert 'Contact: security team.' in p.summary
    assert p.out_of_scope[0].identifier == 'admin.demo.test'
    with pytest.raises(ValueError):
        normalize_self_host({'name': 'Bad', 'url': 'https://bad.test', 'domains': '[app.bad.test]'})


@pytest.mark.parametrize('raw', ['NaN', 'Infinity', '-Infinity', -1, True])
def test_invalid_money_cannot_escape_to_json(raw):
    p = program(min_bounty=raw, max_bounty=raw)
    _apply(p, {'min_bounty': raw, 'max_bounty': raw})
    assert p.min_bounty is None and p.max_bounty is None
    json.dumps(p.to_dict(), allow_nan=False)


def test_money_bounds_and_new_feed_order():
    assert program(min_bounty=500, max_bounty=20).max_bounty is None
    high = program()
    low = program(name='Low', url='https://low.test', offers_bounty=False, min_bounty=None, max_bounty=None)
    for p in (high, low):
        p.first_seen = p.last_seen = '2026-09-12T00:00:00Z'
    cards = build_feeds([low, high], NOW, has_history=True)['new']
    assert cards[0]['id'] == high.id


@pytest.mark.parametrize('value,kind', [('', 'other'), ('https://demo.test/?next=https://github.com', 'url'),
    ('https://github.com.example.test/x', 'url'), ('https://github.com/org/repo', 'repo'), ('nonsense', 'other'),
    ('https://play.google.com/store/apps/x', 'mobile'), ('https://demo.test/*', 'wildcard')])
def test_asset_host_validation(value, kind):
    assert classify_kind(value, 'URL') == kind


def test_full_history_includes_policy_eligibility_outscope_and_removal():
    old = program(out_of_scope=['old.demo.test'])
    new = program(status='paused', max_bounty=500, out_of_scope=['admin.demo.test'])
    new.in_scope[0].eligible_for_bounty = False
    stamp([new], {old.id: old}, NOW)
    diff = diff_snapshot([new], {old.id: old})
    changes = diff['scope_changes'][0]['scopes']
    assert changes['out_of_scope']['added'] == ['admin.demo.test']
    assert changes['in_scope']['updated'][0]['after']['eligible_for_bounty'] is False
    assert diff['program_changes'][0]['fields']['status']['after'] == 'paused'
    history = append_history([], diff, [new], {old.id: old}, '2026-09-12T00:00:00Z')
    assert len(history) == 2
    assert append_history(history, diff, [new], {old.id: old}, '2026-09-12T00:00:00Z') == history
    removed = diff_snapshot([], {old.id: old})
    assert append_history(history, removed, [], {old.id: old}, '2026-09-12T06:00:00Z')[-1]['kind'] == 'removed'


def test_atomic_write_preserves_previous_file_on_failure(tmp_path):
    path = tmp_path/'state.json'
    atomic_json(path, {'good': True})
    with patch('feed_bot.storage.os.replace', side_effect=OSError('interrupted')):
        with pytest.raises(OSError): atomic_json(path, {'good': False})
    assert json.loads(path.read_text()) == {'good': True}
    assert not list(tmp_path.glob('.feed-*'))
    with pytest.raises(ValueError): atomic_json(path, {'number': float('nan')})
    assert json.loads(path.read_text()) == {'good': True}


def test_corrupt_current_uses_backup_without_destroying_it(tmp_path):
    p = program()
    feeds = build_feeds([p], NOW)
    save_snapshot(tmp_path, [p], feeds, {}, [], 'one')
    save_snapshot(tmp_path, [p], feeds, {}, [], 'two')
    current = tmp_path/'programs.min.json'
    current.write_text('{broken')
    assert load_state(tmp_path)['generated_at'] == 'one'
    save_snapshot(tmp_path, [p], feeds, {}, [], 'three')
    assert json.loads((tmp_path/'previous/programs.min.json').read_text())['generated_at'] == 'one'
    assert load_state(tmp_path)['generated_at'] == 'three'


def test_outbox_retries_on_no_diff_run_and_checkpoints_chunks(tmp_path, monkeypatch):
    rows = [{'name': 'A', 'handle': 'a'}]
    fetch = lambda p: rows if p == 'hackerone' else []
    runner(tmp_path, fetch=fetch, now=NOW)
    rows.append({'name': 'B' * 4000, 'handle': 'b'})
    sent = []
    fail = [True]
    def deliver(feeds, diff, statuses, **kwargs):
        for i in range(kwargs['start_part'], len(kwargs['messages'])):
            if fail[0] and i == 1:
                raise RuntimeError('token-must-not-be-persisted')
            sent.append((diff['added'][0]['id'], i))
            kwargs['on_progress'](i + 1)
        return True
    monkeypatch.setattr('feed_bot.pipeline.send_digest', deliver)
    result = runner(tmp_path, fetch=fetch, now=NOW+timedelta(hours=6), send=True)
    assert result['quality']['pending_notifications'] == 1
    assert load_state(tmp_path/'data')['outbox'][0]['next_part'] == 1
    assert 'token-must-not' not in (tmp_path/'data/programs.min.json').read_text()
    fail[0] = False
    result = runner(tmp_path, fetch=fetch, now=NOW+timedelta(hours=12), send=True)
    assert result['diff']['added'] == []
    assert result['telegram_sent'] and result['quality']['pending_notifications'] == 0
    assert sent.count(('hackerone:b', 0)) == 1
    assert len(sent) >= 3
    published = json.loads((tmp_path/'docs/data/feeds.json').read_text())
    assert published['quality']['pending_notifications'] == 0
    assert 'outbox' not in published


def test_telegram_rejects_application_error(monkeypatch):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            return httpx.Response(200, json={'ok': False}, request=httpx.Request('POST', url))
    monkeypatch.setattr('feed_bot.telegram.httpx.Client', Client)
    with pytest.raises(RuntimeError):
        send_digest({}, {}, [], token='fake', chat_id='fake', messages=['hello'])
