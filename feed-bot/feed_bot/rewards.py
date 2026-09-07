from __future__ import annotations

from typing import Any

from feed_bot.models import Program

REWARD_CASH = "cash"
REWARD_SWAG = "swag"
REWARD_HOF = "hall_of_fame"
REWARD_CRYPTO = "crypto"
REWARD_NONE = "none"
REWARD_UNKNOWN = "unknown"

KNOWN = (REWARD_CASH, REWARD_SWAG, REWARD_HOF, REWARD_CRYPTO, REWARD_NONE, REWARD_UNKNOWN)


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    if value in (False, None, "", 0):
        return False
    text = str(value).strip().lower()
    return text in {"yes", "true", "1", "y"}


def infer_reward_types(raw: dict[str, Any] | None = None, *, offers_bounty: bool | None = None) -> list[str]:
    raw = raw or {}
    found: list[str] = []
    if offers_bounty or _truthy(raw.get("offers_bounty") or raw.get("bounty")):
        found.append(REWARD_CASH)
    rewards = raw.get("rewards") or raw.get("reward_types") or []
    if isinstance(rewards, str):
        rewards = [rewards]
    for item in rewards:
        token = str(item).lower().replace("*", "").replace("-", "_").strip()
        if "bounty" in token or token == "cash" or token == "monetary":
            found.append(REWARD_CASH)
        elif "swag" in token or "merch" in token or "hoodie" in token:
            found.append(REWARD_SWAG)
        elif "hall" in token or "recognition" in token or token in {"hof", "kudos"}:
            found.append(REWARD_HOF)
        elif "crypto" in token or token in {"btc", "eth"}:
            found.append(REWARD_CRYPTO)
    if _truthy(raw.get("offers_swag") or raw.get("swag")):
        found.append(REWARD_SWAG)
    hof = raw.get("hall_of_fame") or raw.get("hall_of_fame_url")
    if hof and str(hof).strip() not in {"", "false", "no"}:
        found.append(REWARD_HOF)
    if raw.get("currency") and str(raw.get("currency")).upper() in {"BTC", "ETH", "BZPX"}:
        found.append(REWARD_CRYPTO)
    ordered = []
    for key in (REWARD_CASH, REWARD_CRYPTO, REWARD_SWAG, REWARD_HOF):
        if key in found and key not in ordered:
            ordered.append(key)
    if ordered:
        return ordered
    if offers_bounty is False:
        return [REWARD_NONE]
    if raw.get("offers_bounty") not in (None, "") and not _truthy(raw.get("offers_bounty")):
        return [REWARD_NONE]
    return [REWARD_UNKNOWN]


def attach_derived(program: Program) -> Program:
    kinds = []
    for asset in program.in_scope:
        if asset.kind and asset.kind not in kinds:
            kinds.append(asset.kind)
    program.scope_kinds = kinds
    if not program.reward_types:
        program.reward_types = infer_reward_types(offers_bounty=program.offers_bounty)
    if REWARD_CASH in program.reward_types or REWARD_CRYPTO in program.reward_types:
        program.offers_bounty = True
    return program
