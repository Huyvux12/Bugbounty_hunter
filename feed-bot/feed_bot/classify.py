from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

CONCRETE_KINDS = frozenset({"url", "domain", "repo"})
REPO_HOSTS = ("github.com", "gitlab.com", "bitbucket.org")
MOBILE_HINTS = ("apps.apple.com", "play.google.com", "itunes.apple.com")
MOBILE_TYPES = {
    "ios",
    "android",
    "mobile",
    "apple_store",
    "apple_store_app_id",
    "google_play",
    "google_play_app_id",
}
CONTRACT_TYPES = {"smart_contract", "smartcontract", "blockchain", "contract"}
WILDCARD_TYPES = {"wildcard"}
CIDR_TYPES = {"cidr", "ip_range"}
REPO_TYPES = {"source_code", "sourcecode", "code"}
URL_TYPES = {"url", "website", "web", "web_application", "api"}
DOMAIN_TYPES = {"domain"}

_DOMAIN_RE = re.compile(
    r"^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\.?$",
    re.I,
)


def _norm_type(asset_type: str | None) -> str:
    return (asset_type or "").strip().lower().replace(" ", "_").replace("-", "_")


def classify_kind(identifier: str | None, asset_type: str | None = None) -> str:
    raw = (identifier or "").strip()
    t = _norm_type(asset_type)
    if not raw:
        return "other"
    if t in CONTRACT_TYPES or "smart_contract" in t:
        return "other"
    if t in MOBILE_TYPES:
        return "mobile"
    if t in CIDR_TYPES or _is_cidr(raw):
        return "cidr"
    try:
        parsed = urlparse(raw if "://" in raw else "//" + raw)
        host = (parsed.hostname or "").lower().rstrip(".")
        parsed.port  # Reject malformed ports as well as malformed hosts.
    except ValueError:
        return "other"
    if "*" in host or "*" in parsed.path or t in WILDCARD_TYPES:
        return "wildcard"
    if any(ch.isspace() for ch in raw):
        return "other"
    valid_host = bool(_DOMAIN_RE.fullmatch(host))
    try:
        ipaddress.ip_address(host)
        valid_host = True
    except ValueError:
        pass
    if not valid_host:
        return "other"
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return "other"
    if any(host == h or host.endswith("." + h) for h in MOBILE_HINTS):
        return "mobile"
    if any(host == h or host.endswith("." + h) for h in REPO_HOSTS):
        return "repo"
    if parsed.scheme in {"http", "https"}:
        return "repo" if t in REPO_TYPES else "url"
    if _DOMAIN_RE.fullmatch(raw.rstrip("/")):
        return "domain"
    if t in URL_TYPES and parsed.path:
        return "url"
    return "other"


def is_concrete(kind: str) -> bool:
    return kind in CONCRETE_KINDS


def _is_cidr(value: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False)
        return "/" in value
    except ValueError:
        return False
