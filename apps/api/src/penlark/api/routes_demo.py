"""Demo mode only. These routes return 404 when DEMO_MODE is off."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from penlark import clock, demo
from penlark.api.deps import db, demo_only, get_ctx, owner, writer
from penlark.context import Ctx
from sendora_core.events import record_event

router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(demo_only)])


@router.get("/state", summary="The demo clock")
def state(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx)):
    return {"now": ctx.now(s).isoformat()}


@router.post("/reset", summary="Reset to the seed data and a fresh clock")
def reset(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    try:
        return demo.reset(s, ctx)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except FileNotFoundError as exc:  # raised before anything was erased
        raise HTTPException(503, str(exc)) from exc


@router.post("/tick", summary="Run the jobs once, now: find ideas again and recompute what was learned")
def tick(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    from penlark.jobs import run_cycle

    return run_cycle(s, ctx)


class AdvanceIn(BaseModel):
    hours: float = Field(ge=0, le=24 * 30)


@router.post("/advance", summary="Move the demo clock forward")
def advance(b: AdvanceIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    return {"now": clock.advance(s, b.hours).isoformat()}


class StressIn(BaseModel):
    n: int = Field(ge=1, le=20000)


@router.post("/stress-posts", summary="Add many fictional posts, to check that long tables stay fast")
def stress(b: StressIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    from penlark.models import Performance

    s.bulk_insert_mappings(Performance, [{"post_ref": f"load-{i}", "platform": "linkedin", "posted_on": "2026-01-01", "text": f"Fictional load post {i}. It exists only to fill a long table.", "impressions": 1000, "likes": 20, "comments": 2, "shares": 1, "clicks": 3, "draft_id": None} for i in range(b.n)])
    record_event(s, "demo.stress", None, None, {"n": b.n})
    return {"added": b.n}
