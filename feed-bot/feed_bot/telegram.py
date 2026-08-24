from __future__ import annotations

import os

import httpx

from feed_bot.diff import has_material_diff


def send_digest(
    feeds: dict,
    diff: dict,
    source_status: list[dict],
    pages_url: str | None = None,
    token: str | None = None,
    chat_id: str | None = None,
) -> bool:
    token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    failures = [
        s
        for s in source_status
        if s.get("ok") is False and "missing" not in str(s.get("error") or "").lower()
    ]
    if not has_material_diff(diff) and not failures:
        return False

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
            plus = ", ".join(item.get("added") or []) or "—"
            lines.append(f"• {item['name']}: +{plus}")
    by_platform = feeds.get("recommended_by_platform") or {}
    if by_platform:
        lines.append("")
        lines.append("⭐ Đề xuất theo nền tảng")
        order = ("hackerone", "bugcrowd", "intigriti", "yeswehack", "federacy", "hackenproof")
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
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            url,
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        )
        response.raise_for_status()
    return True
