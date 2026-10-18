import json
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from feed_bot.models import Program, Asset
from feed_bot.rank import build_feeds, score_program
from feed_bot.storage import writer_lock, atomic_json
from feed_bot.store import publish_docs, save_snapshot
from feed_bot.sources.http import get
from feed_bot.sources.selfhost import _from_pd, _from_lissy, _merge
from feed_bot.outbox import enqueue, flush

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def program(**kw):
    return Program(**{'id':'self-host:demo','platform':'self-host','handle':'demo','name':'Demo',
                      'url':'https://demo.test','offers_bounty':True,'status':'open','source':'test','visibility':'public',**kw})


@pytest.mark.parametrize('assets,expected,absent', [
    ([], 'chưa có dữ liệu scope', ['chỉ mobile','chỉ wildcard/CIDR']),
    ([Asset('*.demo.test','URL',True,'wildcard')], 'chỉ wildcard/CIDR', ['chỉ mobile']),
    ([Asset('iOS app','Mobile',True,'mobile')], 'chỉ mobile', ['chỉ wildcard/CIDR']),
])
def test_scope_reasons_do_not_misrepresent_missing_metadata(assets, expected, absent):
    reasons = score_program(program(in_scope=assets), NOW).reasons
    assert expected in reasons
    assert not any(value in reasons for value in absent)


def test_writer_lock_rejects_competing_writer_and_releases_after_error(tmp_path):
    with pytest.raises(ValueError):
        with writer_lock(tmp_path):
            with pytest.raises(RuntimeError, match='Another ingest'):
                with writer_lock(tmp_path):
                    pytest.fail('Competing writer entered')
            raise ValueError('failed run')
    with writer_lock(tmp_path):
        pass


def test_publish_pins_generation_lazy_details_and_preserves_old_manifest_on_failure(tmp_path):
    data, docs = tmp_path/'data', tmp_path/'docs'
    p = program(in_scope=[Asset('hidden.demo.test','URL',True,'domain')])
    private = program(id='private', visibility='access-scoped')
    feeds = build_feeds([p, private], NOW)
    save_snapshot(data, [p, private], feeds, {}, [], NOW.isoformat())
    publish_docs(docs, data, feeds, NOW.isoformat(), None)
    manifest_path = docs/'data/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    base = docs/manifest['base']
    index = json.loads((base/'index.json').read_text())
    assert index['snapshot_id'] == manifest['snapshot_id']
    assert len(index['programs']) == 1
    row = index['programs'][0]
    assert 'in_scope' not in row and 'out_of_scope' not in row
    assert 'hidden.demo.test' in row['search_text']
    detail = json.loads((base/'details'/f"{row['detail_bucket']}.json").read_text())
    assert detail['programs'][p.id]['in_scope'][0]['identifier'] == 'hidden.demo.test'
    assert 'private' not in detail['programs']
    old_bytes = manifest_path.read_bytes()
    original = atomic_json
    def interrupted(path, value):
        if path.name == 'index.json':
            raise OSError('interrupted export')
        original(path, value)
    with patch('feed_bot.store.atomic_json', side_effect=interrupted):
        with pytest.raises(OSError):
            publish_docs(docs, data, {**feeds, 'generated_at':'new'}, 'new', None)
    assert manifest_path.read_bytes() == old_bytes
    assert (base/'index.json').exists()


@pytest.mark.parametrize('status,expected_calls', [(503,3),(429,3),(404,1),(401,1)])
def test_source_retry_is_bounded_and_only_for_transient_errors(status, expected_calls):
    calls, sleeps = [], []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={'Retry-After':'0'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            get(client, 'https://source.test/data', sleeper=sleeps.append)
    assert len(calls) == expected_calls
    assert len(sleeps) == expected_calls - 1


def test_one_bad_record_retains_valid_subsource_records():
    pd = _from_pd([{'name':'Good','url':'https://good.test','domains':['good.test']},
                   {'name':'Bad','url':'https://bad.test','domains':'not a list'}])
    assert len(pd) == 1 and not pd.complete and pd.rejected_count == 1
    lissy = _from_lissy('companies:\n- company: Good\n  url: https://good.test\n- company: Bad\n  url: https://bad.test\n  domains: nope\n')
    assert len(lissy) == 1 and not lissy.complete and lissy.rejected_count == 1


def test_merge_preserves_fallback_fields_regardless_of_input_order():
    low = {'name':'Fallback','url':'https://demo.test','source_dump':'diodb','domains':['app.demo.test']}
    high = {'name':'Official','url':'https://demo.test','source_dump':'lissy93'}
    assert _merge([low, high]) == _merge([high, low])
    assert _merge([low, high])[0]['domains'] == ['app.demo.test']
    assert 'domains' not in high  # No mutation of raw inputs.


def test_repeated_source_alert_is_coalesced_without_dropping_material_events(tmp_path):
    empty = {'added':[], 'removed':[], 'scope_changes':[], 'program_changes':[]}
    statuses = [{'platform':'hackerone','ok':False,'error':'offline'}]
    feeds = {'generated_at':NOW.isoformat()}
    queue = enqueue([], feeds, empty, statuses, None)
    queue = enqueue(queue, {**feeds,'generated_at':'2026-10-18T01:00:00Z'}, empty, statuses, None)
    assert len(queue) == 1 and queue[0]['repeat_count'] == 2
    queue = enqueue(queue, feeds, {**empty,'added':[{'id':'a','name':'A','platform':'hackerone'}]}, statuses, None)
    assert len(queue) == 2
    snapshot = {'generated_at':NOW.isoformat(),'outbox':queue}
    calls = []
    def fail(*args, **kw):
        calls.append(True)
        raise RuntimeError('credential never persisted')
    flush(tmp_path, snapshot, fail)
    flush(tmp_path, snapshot, fail)
    assert len(calls) == 1
    assert 'credential never' not in (tmp_path/'programs.min.json').read_text()
