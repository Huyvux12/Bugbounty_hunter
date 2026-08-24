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
    lowered = raw.lower()

    if not raw and not t:
        return "other"
    if t in CONTRACT_TYPES or "smart_contract" in t:
        return "other"
    if t in MOBILE_TYPES or any(h in lowered for h in MOBILE_HINTS):
        return "mobile"
    if t in CIDR_TYPES or _is_cidr(raw):
        return "cidr"
    if "*" in raw or t in WILDCARD_TYPES:
        return "wildcard"
    if t in REPO_TYPES or any(h in lowered for h in REPO_HOSTS):
        return "repo"
    if lowered.startswith("http://") or lowered.startswith("https://"):
        host = urlparse(raw).hostname or ""
        if "*" in host:
            return "wildcard"
        if any(h in host for h in REPO_HOSTS):
            return "repo"
        return "url"
    if t in URL_TYPES:
        if _DOMAIN_RE.match(raw.rstrip("/")):
            return "domain"
        return "url"
    if t in DOMAIN_TYPES or _DOMAIN_RE.match(raw.rstrip("/")):
        return "domain"
    return "other"


def is_concrete(kind: str) -> bool:
    return kind in CONCRETE_KINDS


def _is_cidr(value: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False)
        return "/" in value
    except ValueError:
        return False
