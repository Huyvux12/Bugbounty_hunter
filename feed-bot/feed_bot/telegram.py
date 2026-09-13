from __future__ import annotations

import os

import httpx

from feed_bot.diff import has_material_diff


def format_digest(feeds: dict, diff: dict, source_status: list[dict], pages_url: str | None = None) -> list[str]:
    failures = [
        s
        for s in source_status
        if s.get("ok") is False and "missing" not in str(s.get("error") or "").lower()
    ]
    if not has_material_diff(diff) and not failures:
        return []

    lines = [f"🦉 Bug bounty feed — {feeds.get('generated_at', '')}"]
    added = diff.get("added") or []
    if added:
        lines.append("")
        lines.append(f"🆕 Mới ({len(added)})")
        for item in added[:8]:
            lines.append(f"• {item['name']} ({item['platform']})")
    changes = diff.get("scope_changes") or []
    if changes:
        lines.append("")
        lines.append(f"🔄 Scope đổi ({len(changes)})")
        for item in changes[:6]:
            plus = ", ".join((item.get("added") or [])[:8]) or "—"
            minus = ", ".join((item.get("removed") or [])[:8]) or "—"
            lines.append(f"• {item['name']}: +{plus}; −{minus}")
            outside = (item.get("scopes") or {}).get("out_of_scope")
            if outside:
                lines.append(f"  Out of scope: +{len(outside['added'])}, −{len(outside['removed'])}, sửa {len(outside['updated'])}")
            updated = (item.get("scopes") or {}).get("in_scope", {}).get("updated", [])
            if updated:
                lines.append(f"  Điều kiện asset đổi: {len(updated)}")
    if diff.get("removed"):
        lines.append("\nĐã ngừng xuất hiện: " + ", ".join(p['name'] for p in diff['removed'][:8]))
    if diff.get("program_changes"):
        lines.append("\nThông tin program đổi")
        for item in diff['program_changes'][:8]:
            lines.append(f"• {item['name']}: " + ", ".join(item['fields']))
    by_platform = feeds.get("recommended_by_platform") or {}
    if by_platform:
        lines.append("")
        lines.append("⭐ Đề xuất theo nền tảng")
        order = ("hackerone", "bugcrowd", "intigriti", "yeswehack", "federacy", "hackenproof", "self-host")
        platforms = [p for p in order if by_platform.get(p)] + sorted(
            p for p in by_platform if p not in order and by_platform.get(p)
        )
        for platform in platforms:
            item = by_platform[platform][0]
            why = ", ".join(item.get("reasons") or []) or "web cụ thể"
            lines.append(f"• {platform}: {item['name']} — {why}")
    else:
        recommended = feeds.get("recommended") or []
        if recommended:
            lines.append("")
            lines.append("⭐ Đề xuất")
            for item in recommended[:5]:
                why = ", ".join(item.get("reasons") or []) or "web cụ thể"
                lines.append(f"• {item['name']} ({item['platform']}) — {why}")
    if failures:
        lines.append("")
        lines.append("⚠️ Nguồn lỗi")
        for item in failures:
            lines.append(f"• {item.get('platform')}: {item.get('error')}")
    if pages_url:
        lines.append("")
        lines.append(pages_url)

    text = "\n".join(lines)
    # 1800 Unicode code points fit below Telegram's limit even with surrogate pairs.
    return [text[i:i + 1800] for i in range(0, len(text), 1800)]


def send_digest(
    feeds: dict,
    diff: dict,
    source_status: list[dict],
    pages_url: str | None = None,
    token: str | None = None,
    chat_id: str | None = None,
    *,
    messages: list[str] | None = None,
    start_part: int = 0,
    on_progress=None,
) -> bool:
    token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    messages = messages if messages is not None else format_digest(feeds, diff, source_status, pages_url)
    if not messages:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with httpx.Client(timeout=30.0) as client:
        for index in range(start_part, len(messages)):
            response = client.post(url, json={"chat_id": chat_id, "text": messages[index], "disable_web_page_preview": True})
            response.raise_for_status()
            # Reject Telegram application errors even when a gateway returns HTTP 200.
            if response.content and response.json().get("ok") is False:
                raise RuntimeError("Telegram rejected the message")
            if on_progress:
                on_progress(index + 1)
    return True
