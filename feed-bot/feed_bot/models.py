from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Asset:
    identifier: str
    asset_type: str
    in_scope: bool
    kind: str
    eligible_for_submission: bool | None = None
    eligible_for_bounty: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Asset:
        return cls(
            identifier=str(data.get("identifier") or ""),
            asset_type=str(data.get("asset_type") or ""),
            in_scope=bool(data.get("in_scope", True)),
            kind=str(data.get("kind") or "other"),
            eligible_for_submission=data.get("eligible_for_submission"),
            eligible_for_bounty=data.get("eligible_for_bounty"),
        )


@dataclass
class Program:
    id: str
    platform: str
    handle: str
    name: str
    url: str
    offers_bounty: bool
    status: str
    source: str
    visibility: str
    in_scope: list[Asset] = field(default_factory=list)
    out_of_scope: list[Asset] = field(default_factory=list)
    min_bounty: float | None = None
    max_bounty: float | None = None
    currency: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None
    concrete_count: int = 0
    easy_score: int = 0
    reasons: list[str] = field(default_factory=list)
    added_assets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Program:
        return cls(
            id=str(data["id"]),
            platform=str(data["platform"]),
            handle=str(data.get("handle") or ""),
            name=str(data.get("name") or ""),
            url=str(data.get("url") or ""),
            offers_bounty=bool(data.get("offers_bounty")),
            status=str(data.get("status") or "unknown"),
            source=str(data.get("source") or ""),
            visibility=str(data.get("visibility") or "public"),
            in_scope=[Asset.from_dict(a) for a in data.get("in_scope") or []],
            out_of_scope=[Asset.from_dict(a) for a in data.get("out_of_scope") or []],
            min_bounty=_maybe_float(data.get("min_bounty")),
            max_bounty=_maybe_float(data.get("max_bounty")),
            currency=data.get("currency"),
            first_seen=data.get("first_seen"),
            last_seen=data.get("last_seen"),
            concrete_count=int(data.get("concrete_count") or 0),
            easy_score=int(data.get("easy_score") or 0),
            reasons=list(data.get("reasons") or []),
            added_assets=list(data.get("added_assets") or []),
        )


def _maybe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def card(program: Program) -> dict[str, Any]:
    return {
        "id": program.id,
        "platform": program.platform,
        "handle": program.handle,
        "name": program.name,
        "url": program.url,
        "offers_bounty": program.offers_bounty,
        "status": program.status,
        "easy_score": program.easy_score,
        "reasons": program.reasons[:4],
        "concrete_count": program.concrete_count,
        "min_bounty": program.min_bounty,
        "max_bounty": program.max_bounty,
        "currency": program.currency,
        "first_seen": program.first_seen,
        "added_assets": program.added_assets[:8],
    }
