"""Background jobs: find ideas again from the notes, and recompute what the performance data says."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from penlark import learning, service
from penlark.context import Ctx, set_state
from penlark.models import Note, Performance
from sendora_core.events import record_event
from sendora_core.jobs import Handler

INTERVALS = {"learn": 3600}


def job_learn(session: Session, ctx: Ctx) -> dict:
    posts = [{"text": p.text, "impressions": p.impressions, "likes": p.likes, "comments": p.comments, "shares": p.shares} for p in session.scalars(select(Performance).order_by(Performance.id.desc()).limit(learning.MAX_POSTS))]
    if len(posts) < 10:
        return {"posts": len(posts), "patterns": 0}
    r = learning.learn(posts)
    patterns = sum(1 for t in r["traits"] if t["status"] == "pattern")
    set_state(session, "learn_summary", f"{len(posts)} posts, {patterns} patterns")
    return {"posts": len(posts), "patterns": patterns}


def job_ideas(session: Session, ctx: Ctx) -> dict:
    return {"ideas": service.load_ideas(session, list(session.scalars(select(Note))), ctx)}


JOBS = {"learn": job_learn}


def make_handlers(ctx: Ctx) -> dict[str, Handler]:
    return {kind: (lambda session, payload, fn=fn: fn(session, ctx)) for kind, fn in JOBS.items()}


def schedule_due(session: Session, ctx: Ctx) -> int:
    from sendora_core.db import utcnow
    from sendora_core.jobs import enqueue
    from sendora_core.models import Job

    n, now = 0, utcnow()
    for kind, secs in INTERVALS.items():
        last = session.scalars(select(Job).where(Job.kind == kind).order_by(Job.id.desc())).first()
        if last is None or (last.status in {"done", "failed"} and last.finished_at is not None and (now - last.finished_at.replace(tzinfo=now.tzinfo)).total_seconds() >= secs):
            enqueue(session, kind)
            n += 1
    return n


def run_cycle(session: Session, ctx: Ctx) -> dict:
    out = {"learn": job_learn(session, ctx)}
    record_event(session, "cycle.ran", None, None, {"patterns": out["learn"]["patterns"]})
    return out
