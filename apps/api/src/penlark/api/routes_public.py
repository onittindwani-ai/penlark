"""The only routes that work without a session: the tracked link redirect and the signed lead webhook."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from penlark import attribution
from penlark.api.deps import db, get_ctx
from penlark.context import Ctx
from penlark.models import Click, Conversion, Link
from sendora_core.ratelimit import RateLimitExceeded

router = APIRouter(tags=["public"])
MAX_WEBHOOK_BYTES = 10_000


async def read_bounded(request: Request, limit: int, message: str = "Too large.") -> bytes:
    """Read a request body, but stop as soon as it is over `limit` bytes: a declared length is checked first, an undeclared one is counted as it arrives."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > limit):
        raise HTTPException(413, message)
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, message)
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/api/public/r/{code}", summary="Record a click and redirect to the stored target (allow list checked again)", include_in_schema=True)
def follow(code: str, request: Request, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx)):
    # request.client.host is already the visitor: uvicorn reads X-Forwarded-For only from the addresses in FORWARDED_ALLOW_IPS. The raw header is typed by the visitor.
    ip = request.client.host if request.client else "x"
    try:
        request.app.state.click_bucket.check(ip)
    except RateLimitExceeded as exc:
        raise HTTPException(429, "Too many requests.") from exc
    link = s.scalars(select(Link).where(Link.code == code)).first() if len(code) <= 20 else None
    if link is None:
        raise HTTPException(404, "This link does not exist.")
    # The target was checked when the link was made and is checked again now, in case the allow list changed. It never comes from the request.
    if not attribution.host_allowed(link.target, ctx.settings.allow_hosts(), ctx.settings.allow_http_local_targets):
        raise HTTPException(410, "This link no longer points at an allowed address.")
    # a visitor is a day scoped hash of address and browser: no address is stored, and the same person on another day is a new visitor
    visitor = hashlib.sha256(f"{ip}|{request.headers.get('user-agent', '')}|{ctx.today(s).isoformat()}|{ctx.settings.session_secret}".encode()).hexdigest()[:16]
    s.add(Click(link_id=link.id, visitor=visitor, at=ctx.now(s)))
    return RedirectResponse(link.target, status_code=302, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


class LeadIn(BaseModel):
    lead_ref: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="lead", pattern="^(lead|customer)$")
    link_code: str | None = Field(default=None, max_length=20)
    value_cents: int = Field(default=0, ge=0, le=10**9)


@router.post("/api/webhooks/lead", summary="A lead or customer event from your form or CRM tool. Signed with LEAD_WEBHOOK_SECRET (header x-penlark-signature, sha256 of the body).")
async def lead(request: Request, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx)):
    raw = await read_bounded(request, MAX_WEBHOOK_BYTES)
    if not attribution.verify_signature(ctx.settings.lead_webhook_secret, raw, request.headers.get("x-penlark-signature")):
        raise HTTPException(401, "The signature is missing or wrong.")
    try:
        body = LeadIn(**json.loads(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "The body is not valid.") from exc
    link = s.scalars(select(Link).where(Link.code == body.link_code)).first() if body.link_code else None
    if s.scalars(select(Conversion).where(Conversion.lead_ref == body.lead_ref, Conversion.kind == body.kind)).first():
        return {"ok": True, "duplicate": True}  # a retry from the sender must not count twice
    s.add(Conversion(link_id=link.id if link else None, lead_ref=body.lead_ref, kind=body.kind, value=body.value_cents, at=ctx.now(s)))
    return {"ok": True, "attributed": link is not None}
