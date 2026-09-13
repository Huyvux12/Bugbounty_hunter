"""Durable, ordered delivery with checkpoints after each successful chunk."""
import hashlib
import json

from feed_bot.storage import atomic_json
from feed_bot.telegram import format_digest


def enqueue(pending, feeds, diff, statuses, pages_url):
    pending = list(pending)
    messages = format_digest(feeds, diff, statuses, pages_url)
    if not messages:
        return pending
    event_id = hashlib.sha256(json.dumps([diff, statuses, feeds['generated_at']], sort_keys=True, allow_nan=False).encode()).hexdigest()
    if not any(item['id'] == event_id for item in pending):
        pending.append({'id': event_id, 'created_at': feeds['generated_at'], 'feeds': feeds, 'diff': diff,
                        'source_status': statuses, 'pages_url': pages_url, 'messages': messages,
                        'next_part': 0, 'attempts': 0})
    return pending


def flush(data_dir, snapshot, deliver, limit=10):
    sent = False
    error = None
    queue = snapshot.setdefault('outbox', [])
    def persist():
        snapshot.setdefault('quality', {})['pending_notifications'] = len(queue)
        atomic_json(data_dir / 'programs.min.json', snapshot)
    for _ in range(min(limit, len(queue))):
        item = queue[0]
        def checkpoint(next_part):
            item['next_part'] = next_part
            persist()
        try:
            ok = deliver(item['feeds'], item['diff'], item['source_status'], pages_url=item['pages_url'],
                         messages=item['messages'], start_part=item['next_part'], on_progress=checkpoint)
        except Exception as exc:
            item['attempts'] += 1
            # URLs in HTTP errors may contain bot credentials; persist only the class.
            error = type(exc).__name__
            item['last_error'] = error
            persist()
            break
        if not ok:
            break
        queue.pop(0)
        sent = True
        persist()
    return sent, error
