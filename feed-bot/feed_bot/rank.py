from __future__ import annotations

from datetime import datetime, timezone

from feed_bot.models import Program, card

MEGA = (
    "google",
    "meta",
    "facebook",
    "microsoft",
    "apple",
    "amazon",
    "tesla",
    "samsung",
    "shopify",
    "uber",
    "paypal",
    "github",
    "gitlab",
    "cloudflare",
    "tiktok",
    "bytedance",
    "oracle",
    "salesforce",
    "adobe",
    "netflix",
    "discord",
    "slack",
    "stripe",
    "coinbase",
    "twitter",
    "nvidia",
    "intel",
    "twilio",
    "robinhood",
    "vercel",
    "ibm",
    "cisco",
    "spotify",
)

LIVE = {"open", "live", "active", ""}
EASY_MIN = 50
RECOMMENDED_LIMIT = 24
PER_PLATFORM_LIMIT = 12
EASY_LIMIT = 50
NEW_LIMIT = 40
PLATFORM_ORDER = (
    "hackerone",
    "bugcrowd",
    "intigriti",
    "yeswehack",
    "federacy",
    "hackenproof",
)


def score_program(program: Program, now: datetime, has_history: bool = False) -> Program:
    reasons: list[str] = []
    score = 0
    kinds = {a.kind for a in program.in_scope}
    concrete = program.concrete_count
    live = program.status in LIVE

    if program.offers_bounty:
        score += 25
        reasons.append("có bounty")
    if concrete >= 1:
        score += 30
        reasons.append(f"{concrete} host/repo cụ thể")
    if concrete >= 3:
        score += 5
    if is_new(program, now, has_history) and not program.added_assets:
        score += 25
        reasons.append("program mới")
    if program.added_assets:
        score += 15
        reasons.append(f"+{len(program.added_assets)} asset")
    if concrete >= 20:
        score -= 15
        reasons.append("scope rộng")

    blob = f"{program.handle} {program.name}".lower()
    if any(name in blob.split() or name == program.handle.lower() for name in MEGA):
        score -= 40
        reasons.append("program lớn, cạnh tranh cao")
    if concrete == 0 and kinds <= {"wildcard", "cidr"}:
        score -= 30
        reasons.append("chỉ wildcard/CIDR")
    if concrete == 0 and kinds <= {"mobile"}:
        score -= 25
        reasons.append("chỉ mobile")
    if kinds <= {"other"} and concrete == 0:
        score -= 20
        reasons.append("không có web/API cụ thể")
    if not live:
        score = min(score, 10)
        reasons.append(f"status={program.status}")

    program.easy_score = max(0, min(100, score))
    program.reasons = reasons
    return program


def is_new(program: Program, now: datetime, has_history: bool) -> bool:
    if not has_history:
        return False
    if program.added_assets:
        return True
    return bool(program.first_seen and program.first_seen == program.last_seen)


def is_easy(program: Program) -> bool:
    if program.status not in LIVE:
        return False
    if program.concrete_count < 1:
        return False
    return program.easy_score >= EASY_MIN


def build_feeds(programs: list[Program], now: datetime, has_history: bool = False) -> dict:
    for program in programs:
        score_program(program, now, has_history=has_history)

    new_items = [p for p in programs if is_new(p, now, has_history) and p.status in LIVE]
    easy_items = [p for p in programs if is_easy(p)]
    new_items.sort(key=lambda p: (p.first_seen or "", -p.easy_score), reverse=True)
    easy_items.sort(key=lambda p: p.easy_score, reverse=True)
    recommended, recommended_by_platform = pick_recommended(easy_items)
    counts = {}
    for program in programs:
        counts[program.platform] = counts.get(program.platform, 0) + 1

    return {
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": counts,
        "recommended": [card(p) for p in recommended],
        "recommended_by_platform": {
            platform: [card(p) for p in rows] for platform, rows in recommended_by_platform.items()
        },
        "easy": [card(p) for p in easy_items[:EASY_LIMIT]],
        "new": [card(p) for p in new_items[:NEW_LIMIT]],
    }


def pick_recommended(easy_items: list[Program]) -> tuple[list[Program], dict[str, list[Program]]]:
    by_platform: dict[str, list[Program]] = {}
    for program in easy_items:
        if program.concrete_count < 1:
            continue
        by_platform.setdefault(program.platform, []).append(program)
    for rows in by_platform.values():
        rows.sort(key=lambda p: p.easy_score, reverse=True)
        del rows[PER_PLATFORM_LIMIT:]

    mixed: list[Program] = []
    seen: set[str] = set()
    platforms = [p for p in PLATFORM_ORDER if p in by_platform] + sorted(
        plat for plat in by_platform if plat not in PLATFORM_ORDER
    )
    max_len = max((len(rows) for rows in by_platform.values()), default=0)
    for index in range(max_len):
        for platform in platforms:
            rows = by_platform[platform]
            if index >= len(rows):
                continue
            program = rows[index]
            if program.id in seen:
                continue
            mixed.append(program)
            seen.add(program.id)
            if len(mixed) >= RECOMMENDED_LIMIT:
                return mixed, by_platform
    return mixed, by_platform
