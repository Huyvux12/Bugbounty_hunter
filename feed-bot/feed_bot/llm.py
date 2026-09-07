from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, Callable

import httpx

from feed_bot.models import Program
from feed_bot.rewards import KNOWN, attach_derived, infer_reward_types

DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_RPM = 15
MAX_PER_RUN = 60
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I | re.M)


class Pace:
    """At most `rpm` HTTP calls per 60s window (including retries)."""

    def __init__(
        self,
        rpm: float,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.min_interval = 60.0 / max(1.0, rpm)
        self._sleeper = sleeper
        self._clock = clock
        self._next = 0.0

    def wait(self) -> None:
        now = self._clock()
        delay = self._next - now
        if delay > 0:
            self._sleeper(delay)
            now = self._clock()
        self._next = now + self.min_interval


def rpm_from_env() -> float:
    raw = os.environ.get("LLM_RPM") or str(DEFAULT_RPM)
    try:
        return max(1.0, float(raw))
    except ValueError:
        return float(DEFAULT_RPM)


def content_hash(program: Program) -> str:
    blob = "|".join(
        [
            program.url,
            program.name,
            program.contact or "",
            program.summary or "",
            program.policy_url or "",
            str(program.offers_bounty),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def copy_cached_llm(programs: list[Program], previous: dict[str, Program]) -> None:
    for program in programs:
        program.content_hash = content_hash(program)
        old = previous.get(program.id)
        if not old:
            continue
        if old.content_hash == program.content_hash and old.llm_status == "ok":
            program.summary_vi = old.summary_vi or program.summary_vi
            if old.reward_types:
                program.reward_types = list(old.reward_types)
            program.llm_status = "ok"
            if old.contact and not program.contact:
                program.contact = old.contact


def enrich_selfhost(programs: list[Program], *, limit: int = MAX_PER_RUN) -> int:
    base = (os.environ.get("LLM_BASE_URL") or "").rstrip("/")
    if not base:
        for program in programs:
            if program.platform == "self-host" and not program.llm_status:
                program.llm_status = "skipped"
        return 0
    key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    model = os.environ.get("LLM_MODEL") or DEFAULT_MODEL
    pace = Pace(rpm_from_env())
    pending = [
        p
        for p in programs
        if p.platform == "self-host" and p.llm_status != "ok"
    ]
    used = 0
    for program in pending[:limit]:
        data = None
        for attempt in range(2):
            try:
                data = _complete(base, key, model, program, pace=pace)
                break
            except Exception:
                if attempt == 0:
                    pace.wait()
        if data is None:
            program.llm_status = "error"
            continue
        _apply(program, data)
        program.llm_status = "ok"
        used += 1
    for program in pending[limit:]:
        if not program.llm_status:
            program.llm_status = "skipped"
    return used


def chat_url(base: str) -> str:
    root = (base or "").rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def _message_text(payload: dict[str, Any]) -> str:
    choice = (payload.get("choices") or [{}])[0]
    if not isinstance(choice, dict):
        return str(payload.get("content") or "")
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
    return str(message.get("content") or delta.get("content") or payload.get("content") or "")


def decode_chat_response(response: httpx.Response) -> dict[str, Any]:
    ctype = response.headers.get("content-type", "")
    text = response.text
    if "event-stream" in ctype or text.lstrip().startswith("data:"):
        parts: list[str] = []
        last: dict[str, Any] = {}
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            obj = json.loads(raw)
            if isinstance(obj, dict):
                last = obj
                chunk = _message_text(obj)
                if chunk:
                    parts.append(chunk)
        if parts:
            return {"choices": [{"message": {"content": "".join(parts)}}]}
        return last
    return response.json()


def _complete(
    base: str,
    api_key: str,
    model: str,
    program: Program,
    pace: Pace | None = None,
) -> dict[str, Any]:
    prompt = (
        "Chuẩn hóa program bug bounty/VDP. Trả JSON thuần, không markdown.\n"
        "is_program, name, summary_vi (2-4 câu tiếng Việt), reward_types "
        "(cash|swag|hall_of_fame|crypto|none|unknown), min_bounty, max_bounty, "
        "currency, contact.\n\n"
        f"name: {program.name}\nurl: {program.url}\n"
        f"contact: {program.contact or ''}\n"
        f"policy: {program.policy_url or ''}\n"
        f"offers_bounty: {program.offers_bounty}\n"
        f"reward_types: {program.reward_types}\n"
        f"min/max: {program.min_bounty}/{program.max_bounty} {program.currency or ''}\n"
        f"summary: {(program.summary or '')[:1200]}\n"
    )
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model,
        "temperature": 0.1,
        "stream": False,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
    }
    if pace:
        pace.wait()
    with httpx.Client(timeout=45.0, follow_redirects=True) as client:
        response = client.post(chat_url(base), headers=headers, json=body)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                extra = float(retry_after) if retry_after else 60.0 / DEFAULT_RPM
            except ValueError:
                extra = 60.0 / DEFAULT_RPM
            time.sleep(max(extra, 60.0 / DEFAULT_RPM))
            response.raise_for_status()
        response.raise_for_status()
        payload = decode_chat_response(response)
    text = _message_text(payload) if isinstance(payload, dict) else ""
    text = _FENCE.sub("", str(text)).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("llm json is not an object")
    return data


def _apply(program: Program, data: dict[str, Any]) -> None:
    if data.get("name"):
        program.name = str(data["name"]).strip() or program.name
    if data.get("summary_vi"):
        program.summary_vi = str(data["summary_vi"]).strip()[:800]
    if data.get("contact") and not program.contact:
        program.contact = str(data["contact"]).strip()
    types = infer_reward_types({"reward_types": data.get("reward_types") or data.get("rewards")})
    if types and types != ["unknown"]:
        program.reward_types = [t for t in types if t in KNOWN] or program.reward_types
    if data.get("min_bounty") not in (None, ""):
        try:
            program.min_bounty = float(data["min_bounty"])
        except (TypeError, ValueError):
            pass
    if data.get("max_bounty") not in (None, ""):
        try:
            program.max_bounty = float(data["max_bounty"])
        except (TypeError, ValueError):
            pass
    if data.get("currency"):
        program.currency = str(data["currency"]).strip()[:8]
    attach_derived(program)
