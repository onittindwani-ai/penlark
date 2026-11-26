from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from penlark import attribution, cadence, dimensions, experiments, fingerprint, learning, service
from penlark.api.bodies import Body
from penlark.api.deps import db, db_read, get_ctx
from penlark.api.serializers import draft_dict, iso
from penlark.api.types import Id, PathId, QueryId
from penlark.context import Ctx
from penlark.match import match
from penlark.models import Author, Click, Conversion, Draft, Experiment, HouseRule, Idea, Link, Note, Performance, Sample, Schedule, Variant, VoiceProfile
from sendora_core.models import Approval, Job

router = APIRouter(prefix="/api", tags=["read"])


@router.get("/overview", summary="Numbers for the top of every page")
def overview(s: Session = Depends(db, scope="function")):
    by = dict(s.execute(select(Draft.status, func.count()).group_by(Draft.status)).all())
    avg_rate = s.execute(select(func.sum(Performance.likes + Performance.comments + Performance.shares), func.sum(Performance.impressions))).one()
    return {"drafts": by, "ideas_inbox": s.scalar(select(func.count()).select_from(Idea).where(Idea.status == "inbox")) or 0, "pending_approvals": s.scalar(select(func.count()).select_from(Approval).where(Approval.status == "pending")) or 0,
            "scheduled": s.scalar(select(func.count()).select_from(Schedule).where(Schedule.status == "planned")) or 0, "posts": s.scalar(select(func.count()).select_from(Performance)) or 0,
            "engagement_rate": round(100 * (avg_rate[0] or 0) / (avg_rate[1] or 1), 2), "clicks": s.scalar(select(func.count()).select_from(Click)) or 0,
            "leads": s.scalar(select(func.count()).select_from(Conversion).where(Conversion.kind == "lead")) or 0}


@router.get("/authors", summary="The voices in this workspace")
def authors(s: Session = Depends(db, scope="function")):
    out = []
    for a in s.scalars(select(Author).order_by(Author.id)):
        p = service.latest_profile(s, a.id, locked_only=True) or service.latest_profile(s, a.id)
        out.append({"id": a.id, "slug": a.slug, "name": a.name, "about": a.about, "samples": s.scalar(select(func.count()).select_from(Sample).where(Sample.author_id == a.id)), "profile_version": p.version if p else None, "locked": bool(p and p.locked)})
    return out


@router.get("/samples", summary="Writing samples of one voice")
def samples(author_id: QueryId, s: Session = Depends(db, scope="function")):
    return [{"id": x.id, "title": x.title, "kind": x.kind, "source": x.source, "words": len(x.text.split()), "text": x.text, "created_at": iso(x.created_at)} for x in s.scalars(select(Sample).where(Sample.author_id == author_id).order_by(Sample.id))]


def _profile_dict(p: VoiceProfile) -> dict:
    return {"id": p.id, "author_id": p.author_id, "version": p.version, "guide": p.guide, "guide_source": p.guide_source, "locked": p.locked, "locked_by": p.locked_by, "diff": p.diff, "n_samples": p.n_samples, "created_at": iso(p.created_at),
            "stats": p.stats, "radar": fingerprint.radar(p.stats), "examples": p.examples, "dimension_meanings": {k: {"label": dimensions.label(k), "meaning": dimensions.meaning(k)} for k in dimensions.ALL}}


@router.get("/profile", summary="The latest voice profile of an author, with its versions")
def profile(author_id: QueryId, s: Session = Depends(db, scope="function")):
    p = service.latest_profile(s, author_id)
    versions = [{"id": v.id, "version": v.version, "locked": v.locked, "n_samples": v.n_samples, "created_at": iso(v.created_at)} for v in s.scalars(select(VoiceProfile).where(VoiceProfile.author_id == author_id).order_by(VoiceProfile.version.desc()))]
    return {"profile": _profile_dict(p) if p else None, "versions": versions}


class CompareIn(Body):
    author_id: Id
    text: str = Field(max_length=20000)


@router.post("/profile/compare", summary="Overlay a text on the profile radar")
def compare(b: CompareIn, s: Session = Depends(db_read, scope="function")):
    from penlark.textstats import measure

    p = service.latest_profile(s, b.author_id)
    if p is None:
        raise HTTPException(404, "Build a voice profile first.")
    m = measure(b.text)
    return {"radar": fingerprint.radar(p.stats, m.values), "match": match(b.text, p.stats, with_sentences=False)}


@router.get("/notes", summary="Calls, comments, emails and notes")
def notes(s: Session = Depends(db, scope="function")):
    return [{"id": n.id, "kind": n.kind, "who": n.who, "text": n.text, "occurred_on": n.occurred_on} for n in s.scalars(select(Note).order_by(Note.occurred_on.desc(), Note.id.desc()))]


@router.get("/ideas", summary="Ranked ideas with evidence quotes")
def ideas_list(status: str | None = None, s: Session = Depends(db, scope="function")):
    q = select(Idea).order_by(Idea.score.desc())
    if status:
        q = q.where(Idea.status == status)
    return [{"id": i.id, "title": i.title, "score": i.score, "parts": i.parts, "status": i.status, "evidence": i.evidence, "note_ids": i.note_ids} for i in s.scalars(q)]


IDEAS_WAIT_SECONDS = 90  # a queued refresh that waited this long is probably waiting for a worker that is not running


@router.get("/ideas/status", summary="The latest Find ideas run: queued, running, done or failed")
def ideas_status(s: Session = Depends(db, scope="function")):
    from datetime import UTC, datetime

    job = s.scalars(select(Job).where(Job.kind == "ideas").order_by(Job.id.desc())).first()
    if job is None:
        return {"status": "none", "job_id": None, "ideas": 0, "message": "No run yet."}
    status, out = job.status, {"job_id": job.id, "ideas": int((job.result or {}).get("ideas", 0))}
    if status == "queued":
        created = job.created_at if job.created_at.tzinfo else job.created_at.replace(tzinfo=UTC)
        waited = int((datetime.now(UTC) - created).total_seconds())
        msg = "Queued. It starts within a few seconds." if waited < IDEAS_WAIT_SECONDS else f"Still queued after {waited // 60 or 1} minute(s). The worker is probably not running: start it with `make worker` (Docker: the worker service), then it will run."
        return {"status": status, "message": msg, **out}
    msg = {"running": "The worker is looking through your notes.", "done": f"Done. {out['ideas']} new idea(s).", "failed": "The last run failed: " + (job.last_error or "no reason was recorded")[:200]}.get(status, status)
    return {"status": status, "message": msg, **out}


@router.get("/drafts", summary="Drafts")
def drafts(status: str | None = None, s: Session = Depends(db, scope="function")):
    q = select(Draft).order_by(Draft.updated_at.desc(), Draft.id.desc())
    if status:
        q = q.where(Draft.status == status)
    return [draft_dict(d) for d in s.scalars(q)]


@router.get("/drafts/{draft_id}", summary="One draft with variants and its live checks")
def draft(draft_id: PathId, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx)):
    d = s.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "No such draft.")
    vs = list(s.scalars(select(Variant).where(Variant.draft_id == d.id).order_by(Variant.id)))
    out = draft_dict(d, vs)
    out["evaluation"] = service.evaluate(s, ctx.settings, d.author_id, d.text, d.source_note_ids, d.claim_links)
    out["variant_scores"] = [{"id": v.id, "score": match(v.text, (service.latest_profile(s, d.author_id, True) or service.latest_profile(s, d.author_id)).stats, with_sentences=False)["score"]} for v in vs]
    return out


@router.get("/schedule", summary="Scheduled and exported drafts, for the calendar")
def schedule(s: Session = Depends(db, scope="function")):
    rows = s.execute(select(Schedule, Draft).join(Draft, Draft.id == Schedule.draft_id).order_by(Schedule.run_on)).all()
    return [{"id": sc.id, "draft_id": sc.draft_id, "title": d.title, "platform": sc.platform, "run_on": sc.run_on, "status": sc.status, "adapter": sc.adapter, "detail": sc.detail} for sc, d in rows]


@router.get("/cadence", summary="Planned posts per week against the posting rhythm")
def cadence_view(weeks: int = Query(4, ge=1, le=12), s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx)):
    targets = cadence.parse(ctx.settings.cadence)
    rows = [(r.platform, r.run_on, r.status) for r in s.scalars(select(Schedule))]
    return {"targets": targets, "weeks": cadence.status(rows, ctx.today(s), targets, weeks)}


@router.get("/rules", summary="House rules and their settings")
def rules(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx)):
    st = ctx.settings
    return {"rules": [{"id": r.id, "kind": r.kind, "value": r.value, "note": r.note, "builtin": r.builtin, "enabled": r.enabled} for r in s.scalars(select(HouseRule).order_by(HouseRule.builtin.desc(), HouseRule.id))],
            "settings": {"no_dashes": st.no_dashes, "max_reading_grade": st.max_reading_grade, "min_voice_match": st.min_voice_match, "require_sources": st.require_sources, "cadence": st.cadence}}


@router.get("/performance", summary="Imported posts with numbers")
def performance(limit: int = Query(5000, ge=1, le=20000), s: Session = Depends(db, scope="function")):
    return [{"id": p.id, "post_ref": p.post_ref, "platform": p.platform, "posted_on": p.posted_on, "text": p.text, "impressions": p.impressions, "likes": p.likes, "comments": p.comments, "shares": p.shares, "clicks": p.clicks,
             "rate": round(100 * (p.likes + p.comments + p.shares) / max(1, p.impressions), 2)} for p in s.scalars(select(Performance).order_by(Performance.posted_on.desc(), Performance.id.desc()).limit(limit))]


@router.get("/learning", summary="What the best posts have in common, with sample sizes")
def learning_view(s: Session = Depends(db, scope="function")):
    posts = [{"text": p.text, "impressions": p.impressions, "likes": p.likes, "comments": p.comments, "shares": p.shares} for p in s.scalars(select(Performance).order_by(Performance.id.desc()).limit(learning.MAX_POSTS))]
    if len(posts) < 10:
        return {"n_posts": len(posts), "traits": [], "tests_run": 0, "warnings": ["Import at least 10 posts with numbers first."]}
    out = learning.learn(posts)
    total = s.scalar(select(func.count()).select_from(Performance)) or 0
    if total > len(posts):
        out["warnings"].append(f"Only the newest {len(posts)} of {total} posts were used, to keep this page quick.")
    return out


@router.get("/links", summary="Tracked links")
def links(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx)):
    return [{"id": l.id, "code": l.code, "short_url": f"{ctx.settings.public_base_url.rstrip('/')}/r/{l.code}", "short_path": f"/r/{l.code}", "base_is_default": ctx.settings.public_base_url.rstrip("/") == "http://localhost:3000", "target": l.target, "post_ref": l.post_ref, "source": l.source, "medium": l.medium, "campaign": l.campaign} for l in s.scalars(select(Link).order_by(Link.id.desc()))]


@router.get("/attribution", summary="Clicks, leads and customers per tracked link")
def attribution_view(s: Session = Depends(db, scope="function")):
    ls = [{"id": l.id, "code": l.code, "post_ref": l.post_ref, "campaign": l.campaign, "source": l.source} for l in s.scalars(select(Link))]
    cl = [{"link_id": c.link_id, "visitor": c.visitor} for c in s.scalars(select(Click))]
    cv = [{"link_id": c.link_id, "kind": c.kind, "value": c.value} for c in s.scalars(select(Conversion))]
    return attribution.funnel(ls, cl, cv)


@router.get("/experiments", summary="A/B experiments with an honest significance note")
def experiments_list(s: Session = Depends(db, scope="function")):
    return [{"id": e.id, "name": e.name, "metric": e.metric, "a_label": e.a_label, "b_label": e.b_label, "a_n": e.a_n, "a_hits": e.a_hits, "b_n": e.b_n, "b_hits": e.b_hits, "status": e.status, "result": experiments.analyse(e.a_n, e.a_hits, e.b_n, e.b_hits)} for e in s.scalars(select(Experiment).order_by(Experiment.id))]
