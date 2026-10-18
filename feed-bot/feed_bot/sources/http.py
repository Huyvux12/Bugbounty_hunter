"""Bounded retries for idempotent source reads, with verified TLS unchanged."""
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx


def get(client, url, *, attempts=3, sleeper=time.sleep):
    for attempt in range(attempts):
        try:
            response = client.get(url)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {408, 429, 500, 502, 503, 504} or attempt + 1 == attempts:
                raise
            raw = exc.response.headers.get("Retry-After", "")
            try:
                delay = float(raw)
            except ValueError:
                try:
                    delay = (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    delay = 2 ** attempt
            # A long server-requested pause is deferred to the next scheduled run,
            # rather than retrying earlier than Retry-After.
            if delay > 10:
                raise
            sleeper(max(0, delay))
        except httpx.TransportError:
            if attempt + 1 == attempts:
                raise
            sleeper(2 ** attempt)
