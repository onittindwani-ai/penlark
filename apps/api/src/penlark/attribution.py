"""Tracked links and lead attribution.

The redirect is the one public route, so it is the one place an attacker could aim an open redirect. A link can only point at a URL whose host is on the allow list
(set by the owner), the scheme is https (http only for local development), and the target is stored when the link is made, never taken from the click request.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


class LinkError(ValueError):
    pass


def host_allowed(url: str, allow: list[str], allow_http_local: bool = False) -> bool:
    u = urlparse(url)
    if u.scheme not in ({"https", "http"} if allow_http_local else {"https"}) or not u.hostname or u.username or u.password:
        return False
    host = u.hostname.lower().rstrip(".")
    return any(host == a.lower() or host.endswith("." + a.lower()) for a in allow if a)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def make_target(url: str, allow: list[str], source: str, medium: str, campaign: str, content: str = "", allow_http_local: bool = False) -> str:
    if not host_allowed(url, allow, allow_http_local):
        raise LinkError("That address is not on your allow list, or it is not https. Add the host under Attribution settings first.")
    u = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if not k.startswith("utm_")]
    q += [("utm_source", slug(source)), ("utm_medium", slug(medium)), ("utm_campaign", slug(campaign))]
    if content:
        q.append(("utm_content", slug(content)))
    return urlunparse(u._replace(query=urlencode(q), fragment=""))


def new_code(taken: set[str] | None = None, rng: secrets.SystemRandom | None = None) -> str:
    rng = rng or secrets.SystemRandom()
    for _ in range(50):
        c = "".join(rng.choice(ALPHABET) for _ in range(7))
        if not taken or c not in taken:
            return c
    raise LinkError("Could not make a free short code. Try again.")


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not secret or not header:
        return False
    return hmac.compare_digest(sign(secret, body), header.removeprefix("sha256=").strip())


def funnel(links: list[dict], clicks: list[dict], conversions: list[dict]) -> dict:
    """Per link and per post: clicks, unique clicks (by hashed visitor token), conversions, and the rate. Rates carry the count they came from."""
    by: dict[int, dict] = {l["id"]: {**l, "clicks": 0, "unique": set(), "leads": 0, "customers": 0, "value": 0} for l in links}
    for c in clicks:
        if c["link_id"] in by:
            by[c["link_id"]]["clicks"] += 1
            by[c["link_id"]]["unique"].add(c.get("visitor", ""))
    for cv in conversions:
        row = by.get(cv.get("link_id"))
        if row:
            if cv["kind"] == "lead":
                row["leads"] += 1
            elif cv["kind"] == "customer":
                row["customers"] += 1
                row["value"] += cv.get("value", 0)
    rows = []
    for r in by.values():
        u = len(r.pop("unique"))
        r["unique_clicks"] = u
        r["lead_rate"] = round(100 * r["leads"] / u, 1) if u else None
        rows.append(r)
    tot = {"links": len(rows), "clicks": sum(r["clicks"] for r in rows), "unique_clicks": sum(r["unique_clicks"] for r in rows), "leads": sum(r["leads"] for r in rows), "customers": sum(r["customers"] for r in rows), "value": sum(r["value"] for r in rows)}
    return {"links": sorted(rows, key=lambda r: (-r["leads"], -r["clicks"])), "totals": tot, "note": "Counts, not proof of cause: a person may have seen the post and typed the address later. Links count only people who clicked."}
