from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from penlark import service
from penlark.api.deps import db, get_ctx, owner, writer
from penlark.api.serializers import iso
from penlark.api.types import PathId
from penlark.context import Ctx, set_state
from penlark.models import Draft
from penlark.registry import CATEGORIES, ENV_VARS
from sendora_core.approvals import ApprovalError, decide
from sendora_core.audit import record_audit, verify_audit_chain
from sendora_core.models import Approval, AuditEntry

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/approvals", summary="Pending and recent approvals")
def approvals(s: Session = Depends(db, scope="function")):
    rows = list(s.scalars(select(Approval).order_by(Approval.id.desc()).limit(100)))
    drafts = {d.id: d for d in s.scalars(select(Draft).where(Draft.id.in_([int(a.payload.get("draft_id", 0)) for a in rows if a.action == "draft.approve"] or [-1])))}
    return [{"preview": _preview(a, drafts), "id": a.id, "action": a.action, "summary": a.summary, "risk": a.risk, "status": a.status, "requested_by": a.requested_by, "decided_by": a.decided_by, "note": a.decision_note, "created_at": iso(a.created_at), "payload": a.payload} for a in rows]


PAST_PREVIEW_CHARS = 1200  # a decided approval shows only the start of its draft; a waiting one shows every character


def _preview(a: Approval, drafts: dict) -> dict | None:
    """What the person is about to approve: the whole draft text as it is now, and its fingerprint, so nobody approves a title or the first lines alone.
    The fingerprint is sent back with the decision, so a draft that changed after it was opened cannot be approved by mistake."""
    d = drafts.get(int(a.payload.get("draft_id", 0))) if a.action == "draft.approve" else None
    if d is None:
        return None
    full = a.status == "pending"
    return {"draft_id": d.id, "text": d.text if full else d.text[:PAST_PREVIEW_CHARS], "truncated": not full and len(d.text) > PAST_PREVIEW_CHARS, "text_sha256": service.text_digest(d.text),
            "approved_text_sha256": (a.payload or {}).get("text_sha256"), "status": d.status, "author_id": d.author_id}


class DecideIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=500)
    text_sha256: str | None = Field(default=None, max_length=64)  # the fingerprint of the text the person was shown, when the app sends it


@router.post("/approvals/{approval_id}/decide", summary="Approve or reject. The person who asked cannot decide.")
def decide_approval(approval_id: PathId, body: DecideIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    pre = s.get(Approval, approval_id)
    if pre is not None and pre.action == "draft.approve" and pre.status == "pending" and body.approve:
        # Hold the draft row, then check the words are still the words this approval was asked for (and the ones this person was shown).
        d0 = service.lock_draft(s, int((pre.payload or {}).get("draft_id", 0)))
        seen = service.text_digest(d0.text) if d0 is not None else None
        if d0 is None or (pre.payload or {}).get("text_sha256") != seen:
            raise HTTPException(409, "This draft was changed after it was sent for approval. Ask for approval again.")
        if body.text_sha256 is not None and body.text_sha256 != seen:
            raise HTTPException(409, "The draft changed since you opened it. Read it again before you approve.")
    try:
        a = decide(s, approval_id, body.approve, u["user"], u["role"], body.note or None)
    except ApprovalError as exc:
        raise HTTPException(409, str(exc)) from exc
    if a.action == "draft.approve" and body.approve:
        d = s.get(Draft, int(a.payload.get("draft_id", 0)))
        if d is None or d.approval_id != a.id or d.status != "pending_approval":
            raise HTTPException(409, "This draft was changed or handled after it was sent for approval. Ask for approval again.")  # the base already marked it approved: the session rolls back
        why = service.readiness_problem(service.evaluate(s, ctx.settings, d.author_id, d.text, d.source_note_ids, d.claim_links), ctx.settings.min_voice_match)
        if why:
            raise HTTPException(409, "It no longer passes the checks. " + why)
    if a.action == "draft.approve":
        d = s.get(Draft, int(a.payload.get("draft_id", 0)))
        if d is not None and d.approval_id == a.id:
            d.status = "approved" if body.approve else "rejected"
            d.updated_at = ctx.now(s)
            record_audit(s, u["user"], "draft.approved" if body.approve else "draft.rejected", f"draft:{d.id}", {"approval": a.id})
    return {"status": a.status}


@router.get("/audit", summary="Audit log, newest first")
def audit(limit: int = Query(100, ge=1, le=1000), s: Session = Depends(db, scope="function")):
    return [{"id": e.id, "actor": e.actor, "action": e.action, "target": e.target, "detail": e.detail, "at": e.created_at} for e in s.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit))]


@router.get("/audit/verify", summary="Check the audit chain has not been edited")
def audit_verify(s: Session = Depends(db, scope="function")):
    ok, bad = verify_audit_chain(s)
    return {"ok": ok, "first_bad_id": bad}


@router.get("/integrations", summary="Every adapter, which one is selected, and what it needs")
def integrations(ctx: Ctx = Depends(get_ctx)):
    st = ctx.settings
    chosen = {c: getattr(st, f"{c}_adapter") for c in CATEGORIES}
    out = []
    for row in ctx.registry.describe():
        env = ENV_VARS.get((row["category"], row["name"]), [])
        out.append({**row, "selected": chosen.get(row["category"]) == row["name"], "env_vars": env, "configured": all(bool(getattr(st, v.lower(), "")) for v in env) if env else True})
    return {"categories": list(CATEGORIES), "adapters": out, "demo_mode": st.demo_mode, "allow_hosts": st.allow_hosts(), "platform_note": "Posting to LinkedIn, X, Instagram and the other networks needs each platform's own app approval. The scheduler tool you pick holds that approval; Penlark does not."}


@router.post("/integrations/{category}/test", summary="Test the selected adapter in a category")
def test_integration(category: str, ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    if category not in CATEGORIES:
        raise HTTPException(404, "Unknown category.")
    ok, detail = ctx.scheduler.healthcheck()
    return {"category": category, "ok": ok, "detail": detail}


@router.get("/settings", summary="Mode, kill switch and config problems")
def get_settings(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx)):
    eff, st = ctx.effective(s), ctx.settings
    return {"mode": st.mode.value, "effective_mode": eff.mode.value, "kill_switch": eff.kill_switch, "demo_mode": st.demo_mode, "problems": st.problems(), "writer": "offline templates (not a language model)" if st.effective_llm_backend.value == "offline" else f"model backend: {st.effective_llm_backend.value}",
            "scheduler": st.scheduler_adapter, "rules": {"no_dashes": st.no_dashes, "max_reading_grade": st.max_reading_grade, "min_voice_match": st.min_voice_match}}


class SettingsIn(BaseModel):
    kill_switch: bool | None = None
    force_draft: bool | None = None


@router.post("/settings", summary="Turn the kill switch or draft mode on or off (owner only). The app can never switch live mode on.")
def post_settings(body: SettingsIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    if body.kill_switch is not None:
        set_state(s, "kill_switch", "1" if body.kill_switch else "0")
        record_audit(s, u["user"], "settings.kill_switch", None, {"on": body.kill_switch})
    if body.force_draft is not None:
        set_state(s, "force_draft", "1" if body.force_draft else "0")
        record_audit(s, u["user"], "settings.force_draft", None, {"on": body.force_draft})
    s.flush()
    return get_settings(s, ctx)
