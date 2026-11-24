from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from penlark import attribution, ingest, learning, service
from penlark.api.deps import db, get_ctx, writer
from penlark.api.serializers import draft_dict
from penlark.context import Ctx
from penlark.match import match
from penlark.models import Author, Draft, Experiment, HouseRule, Idea, Link, Note, Performance, Sample, Schedule, Variant, VoiceProfile
from sendora_core.approvals import request_approval
from sendora_core.audit import record_audit
from sendora_core.adapters import AdapterError
from sendora_core.safety import SafetyError

router = APIRouter(prefix="/api", tags=["write"])


def _rule(fn, *a, **k):
    try:
        return fn(*a, **k)
    except (service.RuleError, ingest.IngestError, learning.ImportError_, attribution.LinkError) as exc:
        raise HTTPException(400, str(exc)) from exc


class MatchIn(BaseModel):
    author_id: int
    text: str = Field(max_length=30000)
    source_note_ids: list[int] = []
    claim_links: dict[str, int] = {}


@router.post("/match", summary="Live voice match and house rule check of any text. Writes nothing.")
def live_match(b: MatchIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx)):
    return service.evaluate(s, ctx.settings, b.author_id, b.text, b.source_note_ids, b.claim_links)


class SampleIn(BaseModel):
    author_id: int
    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=20, max_length=200000)
    kind: str = "text"  # text, markdown, transcript


def _has_sample(s: Session, author_id: int, text: str) -> bool:
    """The same text twice would count double in the voice profile."""
    key = " ".join(text.split()).lower()
    return any(" ".join(t.split()).lower() == key for t in s.scalars(select(Sample.text).where(Sample.author_id == author_id)))


@router.post("/samples", summary="Add a pasted writing sample, transcript or markdown")
def add_sample(b: SampleIn, s: Session = Depends(db), u: dict = Depends(writer)):
    item = _rule(lambda: ingest.from_transcript(b.text, b.title) if b.kind == "transcript" else ingest.from_markdown(b.text, b.title) if b.kind == "markdown" else ingest.from_text(b.text, b.title))
    if s.get(Author, b.author_id) is None:
        raise HTTPException(404, "No such voice.")
    if _has_sample(s, b.author_id, item.text):
        raise HTTPException(409, "That text is already in this voice's library.")
    row = Sample(author_id=b.author_id, title=item.title[:200], kind=item.kind, text=item.text, source="pasted")
    s.add(row)
    s.flush()
    record_audit(s, u["user"], "sample.added", f"sample:{row.id}", {"words": len(item.text.split())})
    return {"id": row.id, "title": row.title}


@router.post("/samples/upload", summary="Upload a file: text, markdown, PDF, transcript, LinkedIn Shares.csv or X tweets.js")
async def upload_sample(request: Request, author_id: int, s: Session = Depends(db), u: dict = Depends(writer)):
    name = (request.headers.get("x-filename") or "upload.txt")[:200]
    data = await request.body()
    if s.get(Author, author_id) is None:
        raise HTTPException(404, "No such voice.")
    items = _rule(ingest.detect, name, data)
    fresh = [it for it in items if not _has_sample(s, author_id, it.text)]
    for it in fresh:
        s.add(Sample(author_id=author_id, title=it.title[:200], kind=it.kind, text=it.text, source=f"file {name}"))
        s.flush()
    record_audit(s, u["user"], "sample.uploaded", name, {"items": len(fresh), "skipped": len(items) - len(fresh)})
    return {"added": len(fresh), "skipped": len(items) - len(fresh)}


@router.delete("/samples/{sample_id}", summary="Remove a sample")
def delete_sample(sample_id: int, s: Session = Depends(db), u: dict = Depends(writer)):
    row = s.get(Sample, sample_id)
    if row is None:
        raise HTTPException(404, "No such sample.")
    s.delete(row)
    record_audit(s, u["user"], "sample.removed", f"sample:{sample_id}", {})
    return {"ok": True}


class BuildIn(BaseModel):
    author_id: int


@router.post("/profile/build", summary="Measure the samples and make a new profile version (not locked)")
def build(b: BuildIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    p = _rule(service.build_profile, s, b.author_id, u["user"], ctx)
    return {"id": p.id, "version": p.version, "diff": p.diff}


class GuideIn(BaseModel):
    guide: str = Field(max_length=6000)


@router.put("/profile/{profile_id}/guide", summary="Edit the guide. A locked profile cannot be edited, build a new version instead.")
def edit_guide(profile_id: int, b: GuideIn, s: Session = Depends(db), u: dict = Depends(writer)):
    p = s.get(VoiceProfile, profile_id)
    if p is None:
        raise HTTPException(404, "No such profile.")
    if p.locked:
        raise HTTPException(409, "This version is locked. Build a new version to change the guide.")
    p.guide, p.guide_source = b.guide, "edited by a person"
    record_audit(s, u["user"], "profile.guide_edited", f"profile:{p.id}", {})
    return {"ok": True}


@router.post("/profile/{profile_id}/lock", summary="Lock a profile so scores use a fixed voice")
def lock(profile_id: int, s: Session = Depends(db), u: dict = Depends(writer)):
    p = s.get(VoiceProfile, profile_id)
    if p is None:
        raise HTTPException(404, "No such profile.")
    p.locked, p.locked_by = True, u["user"]
    record_audit(s, u["user"], "profile.locked", f"profile:{p.id}", {"version": p.version})
    return {"ok": True}


class NoteIn(BaseModel):
    kind: str = Field(pattern="^(call|comment|email|note|fact)$")
    who: str = Field(default="", max_length=200)
    text: str = Field(min_length=8, max_length=20000)
    occurred_on: str = Field(default="", max_length=10)


@router.post("/notes", summary="Add a call, comment, email, note or a founder fact")
def add_note(b: NoteIn, s: Session = Depends(db), u: dict = Depends(writer)):
    if len(b.text.strip()) < 8:
        raise HTTPException(400, "Write at least a short sentence.")
    row = Note(kind=b.kind, who=b.who.strip(), text=b.text.strip(), occurred_on=b.occurred_on)
    s.add(row)
    s.flush()
    record_audit(s, u["user"], "note.added", f"note:{row.id}", {"kind": b.kind})
    return {"id": row.id}


@router.post("/ideas/refresh", summary="Find ideas again from all notes")
def refresh(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    n = service.load_ideas(s, list(s.scalars(select(Note))), ctx)
    record_audit(s, u["user"], "ideas.refreshed", None, {"ideas": n})
    return {"ideas": n}


@router.post("/ideas/{idea_id}/drop", summary="Drop an idea")
def drop(idea_id: int, s: Session = Depends(db), u: dict = Depends(writer)):
    i = s.get(Idea, idea_id)
    if i is None:
        raise HTTPException(404, "No such idea.")
    i.status = "dropped"
    return {"ok": True}


class DraftFromIdea(BaseModel):
    author_id: int
    kind: str = Field(default="post", pattern="^(post|script|email|newsletter)$")


@router.post("/ideas/{idea_id}/draft", summary="Write a draft from an idea in a chosen voice (offline stand in)")
def draft_from_idea(idea_id: int, b: DraftFromIdea, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = _rule(service.create_drafts_from_idea, s, ctx, idea_id, b.author_id, b.kind, u["user"])
    return {"id": d.id}


class DraftIn(BaseModel):
    text: str = Field(max_length=30000)
    author_id: int | None = None
    title: str | None = Field(default=None, max_length=200)
    source_note_ids: list[int] | None = None
    claim_links: dict[str, int] | None = None


@router.put("/drafts/{draft_id}", summary="Edit a draft. Editing an approved draft sends it back to draft.")
def edit_draft(draft_id: int, b: DraftIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = s.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "No such draft.")
    if d.status in {"exported", "published"}:
        raise HTTPException(409, "This draft was already exported. Copy it into a new draft to change it.")
    if b.author_id is not None and s.get(Author, b.author_id) is None:
        raise HTTPException(404, "No such voice.")
    changed = b.text != d.text or (b.author_id is not None and b.author_id != d.author_id)
    d.text = b.text
    if b.author_id is not None:
        d.author_id = b.author_id
    if b.title is not None:
        d.title = b.title
    if b.source_note_ids is not None:
        d.source_note_ids = b.source_note_ids
    if b.claim_links is not None:
        d.claim_links = b.claim_links
    if changed and d.status in {"approved", "pending_approval", "scheduled"}:
        if d.status == "pending_approval":
            service.withdraw_approval(s, d, u["user"], "The draft was edited after it was sent for approval.")
        d.status = "draft"  # an edit voids the approval
        record_audit(s, u["user"], "draft.approval_voided", f"draft:{d.id}", {})
    d.updated_at = ctx.now(s)
    return draft_dict(d)


@router.post("/drafts/{draft_id}/variants/{variant_id}/use", summary="Replace the draft text with a variant")
def use_variant(draft_id: int, variant_id: int, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d, v = s.get(Draft, draft_id), s.get(Variant, variant_id)
    if d is None or v is None or v.draft_id != d.id:
        raise HTTPException(404, "No such variant.")
    if d.status in {"exported", "published"}:
        raise HTTPException(409, "This draft was already exported. Copy it into a new draft to change it.")
    if d.status == "pending_approval":
        service.withdraw_approval(s, d, u["user"], "The draft was changed after it was sent for approval.")
    d.text, d.status, d.updated_at = v.text, "draft", ctx.now(s)
    return draft_dict(d)


@router.post("/drafts/{draft_id}/request-approval", summary="Ask a second person to approve this draft")
def request(draft_id: int, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = s.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "No such draft.")
    if d.status not in {"draft", "rejected"}:
        raise HTTPException(409, "This draft is already waiting or approved.")
    ev = service.evaluate(s, ctx.settings, d.author_id, d.text, d.source_note_ids, d.claim_links)
    why = service.readiness_problem(ev, ctx.settings.min_voice_match)
    if why:
        raise HTTPException(409, why)
    a = request_approval(s, "draft.approve", f"Approve draft: {d.title}", {"draft_id": d.id, "match": ev["match"]["score"]}, "medium", u["user"])
    d.status, d.approval_id = "pending_approval", a.id
    return {"approval_id": a.id}


class ScheduleIn(BaseModel):
    platform: str = Field(default="linkedin", pattern="^(linkedin|x|instagram|facebook|threads|youtube|newsletter|email)$")
    run_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/drafts/{draft_id}/schedule", summary="Put an approved draft on the calendar (a plan, nothing is sent)")
def schedule(draft_id: int, b: ScheduleIn, s: Session = Depends(db), u: dict = Depends(writer)):
    d = s.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "No such draft.")
    if d.status not in {"approved", "scheduled"}:
        raise HTTPException(409, "Only an approved draft can go on the calendar. Ask a second person to approve it first.")
    try:
        datetime.strptime(b.run_on, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "That is not a real date.") from exc
    row = Schedule(draft_id=d.id, platform=b.platform, run_on=b.run_on, status="planned", adapter="plan")
    s.add(row)
    d.status = "scheduled"
    s.flush()
    record_audit(s, u["user"], "draft.scheduled", f"draft:{d.id}", {"run_on": b.run_on, "platform": b.platform})
    return {"id": row.id}


class MoveIn(BaseModel):
    run_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.put("/schedule/{schedule_id}", summary="Move a planned item to another day (drag on the calendar)")
def move(schedule_id: int, b: MoveIn, s: Session = Depends(db), u: dict = Depends(writer)):
    row = s.get(Schedule, schedule_id)
    if row is None:
        raise HTTPException(404, "No such item.")
    if row.status != "planned":
        raise HTTPException(409, "Only a planned item can be moved.")
    try:
        datetime.strptime(b.run_on, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "That is not a real date.") from exc
    old, row.run_on = row.run_on, b.run_on
    record_audit(s, u["user"], "schedule.moved", f"schedule:{row.id}", {"from": old, "to": b.run_on})
    return {"ok": True, "from": old}


@router.delete("/schedule/{schedule_id}", summary="Take an item off the calendar")
def unschedule(schedule_id: int, s: Session = Depends(db), u: dict = Depends(writer)):
    row = s.get(Schedule, schedule_id)
    if row is None:
        raise HTTPException(404, "No such item.")
    d = s.get(Draft, row.draft_id)
    s.delete(row)
    s.flush()
    if d and d.status == "scheduled" and not s.scalar(select(Schedule.id).where(Schedule.draft_id == d.id)):
        d.status = "approved"
    return {"ok": True}


class ExportIn(BaseModel):
    platform: str | None = Field(default=None, pattern="^(linkedin|x|instagram|facebook|threads|youtube|newsletter|email)$")


@router.post("/drafts/{draft_id}/export", summary="Save an approved draft to a file to copy and post yourself (the default way out)")
def export(draft_id: int, b: ExportIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = s.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "No such draft.")
    if d.status not in {"approved", "scheduled"}:
        raise HTTPException(409, "Only an approved draft can be exported. Ask a second person to approve it first.")
    planned = list(s.scalars(select(Schedule).where(Schedule.draft_id == d.id, Schedule.status == "planned").order_by(Schedule.id)))
    platform = b.platform or (planned[0].platform if planned else "linkedin")  # a draft planned for X is exported for X
    try:
        res = ctx.scheduler.export(d.id, d.title, platform, d.text)
    except (AdapterError, SafetyError) as exc:
        raise HTTPException(409, str(exc)) from exc
    if planned:  # the planned day becomes the exported day: one entry per draft on the calendar, not a planned one and an exported one
        keep = planned[0]
        keep.platform, keep.status, keep.adapter, keep.external_id, keep.detail = platform, "exported", ctx.scheduler.name, res["external_id"], res["detail"]
        for extra in planned[1:]:
            s.delete(extra)
    else:
        s.add(Schedule(draft_id=d.id, platform=platform, run_on=ctx.today(s).isoformat(), status="exported", adapter=ctx.scheduler.name, external_id=res["external_id"], detail=res["detail"]))
    d.status = "exported"
    record_audit(s, u["user"], "draft.exported", f"draft:{d.id}", {"adapter": ctx.scheduler.name, "platform": platform})
    return res


class SendIn(BaseModel):
    platform: str = "linkedin"
    channel_id: str = Field(min_length=1, max_length=120)
    confirm: bool = False
    as_draft: bool = True
    run_on: str | None = None


@router.post("/drafts/{draft_id}/send", summary="Send an approved draft to Postiz, Buffer or Metricool. Needs live mode, an approval and confirm.")
def send(draft_id: int, b: SendIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = s.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "No such draft.")
    eff = ctx.effective(s)
    sched = ctx.scheduler
    if not hasattr(sched, "send") or sched.name in {"export", "seed"}:
        raise HTTPException(409, "The file export never sends. Choose Postiz, Buffer or Metricool in the settings.")
    when = datetime.strptime(b.run_on, "%Y-%m-%d").replace(tzinfo=timezone.utc) if b.run_on else ctx.now(s) + timedelta(days=1)
    try:
        sched.s = eff  # the effective settings carry the kill switch and the draft mode pull back
        res = sched.send(d.text, b.platform, when, b.channel_id, approved=d.status in {"approved", "scheduled"}, confirm=b.confirm, as_draft=b.as_draft)
    except (AdapterError, SafetyError) as exc:
        raise HTTPException(409, str(exc)) from exc
    s.add(Schedule(draft_id=d.id, platform=b.platform, run_on=when.date().isoformat(), status="sent", adapter=sched.name, external_id=res["external_id"], detail=res["detail"]))
    d.status = "published" if not b.as_draft else "scheduled"
    record_audit(s, u["user"], "draft.sent", f"draft:{d.id}", {"adapter": sched.name, "as_draft": b.as_draft})
    return res


class RuleIn(BaseModel):
    kind: str = Field(pattern="^(phrase|pattern)$")
    value: str = Field(min_length=2, max_length=300)
    note: str = Field(default="", max_length=300)


@router.post("/rules", summary="Add a banned phrase or pattern")
def add_rule(b: RuleIn, s: Session = Depends(db), u: dict = Depends(writer)):
    if b.kind == "pattern":
        import re

        try:
            re.compile(b.value)
        except re.error as exc:
            raise HTTPException(400, "That pattern is not valid: " + str(exc)[:100]) from exc
        if len(b.value) > 200:
            raise HTTPException(400, "Keep patterns under 200 characters.")
    value = b.value.strip()
    if len(value) < 2:
        raise HTTPException(400, "Type at least two characters.")
    if any(r.value.strip().lower() == value.lower() and r.kind == b.kind for r in s.scalars(select(HouseRule))):
        raise HTTPException(409, "That rule is already in the list." )
    row = HouseRule(kind=b.kind, value=value, note=b.note)
    s.add(row)
    s.flush()
    record_audit(s, u["user"], "rule.added", f"rule:{row.id}", {"kind": b.kind})
    return {"id": row.id}


class RuleToggle(BaseModel):
    enabled: bool


@router.put("/rules/{rule_id}", summary="Turn a rule on or off")
def toggle_rule(rule_id: int, b: RuleToggle, s: Session = Depends(db), u: dict = Depends(writer)):
    r = s.get(HouseRule, rule_id)
    if r is None:
        raise HTTPException(404, "No such rule.")
    r.enabled = b.enabled
    record_audit(s, u["user"], "rule.toggled", f"rule:{rule_id}", {"enabled": b.enabled})
    return {"ok": True}


@router.delete("/rules/{rule_id}", summary="Delete your own rule (built in rules can only be turned off)")
def delete_rule(rule_id: int, s: Session = Depends(db), u: dict = Depends(writer)):
    r = s.get(HouseRule, rule_id)
    if r is None:
        raise HTTPException(404, "No such rule.")
    if r.builtin:
        raise HTTPException(409, "Built in rules can be turned off, not deleted.")
    s.delete(r)
    return {"ok": True}


class ImportIn(BaseModel):
    csv: str = Field(max_length=5_000_000)
    mapping: dict[str, str] | None = None
    preview: bool = True


@router.post("/performance/import", summary="Import post numbers from CSV. With preview true nothing is saved.")
def import_csv(b: ImportIn, s: Session = Depends(db), u: dict = Depends(writer)):
    import csv, io

    headers = next(csv.reader(io.StringIO(b.csv)), [])
    sug = learning.suggest_mapping(headers)
    mapping = b.mapping or sug
    try:
        rows, problems = learning.parse_csv(b.csv, mapping)
    except learning.ImportError_ as exc:
        return {"ok": False, "headers": headers, "suggested": sug, "message": str(exc), "rows": 0, "problems": []}
    # the same file imported twice must not count every post twice, or the learning loop learns from copies
    key = lambda text, day, views: (" ".join(text.split()).lower(), day, views)  # noqa: E731
    seen = {key(t, d, i) for t, d, i in s.execute(select(Performance.text, Performance.posted_on, Performance.impressions))}
    fresh, dupes = [], 0
    for r in rows:
        k = key(r["text"], r["posted_on"], r["impressions"])
        if k in seen:
            dupes += 1
            continue
        seen.add(k)
        fresh.append(r)
    if not b.preview:
        for r in fresh:
            s.add(Performance(**r))
        record_audit(s, u["user"], "performance.imported", None, {"rows": len(fresh), "skipped": len(problems), "duplicates": dupes})
    return {"ok": True, "headers": headers, "suggested": sug, "rows": len(fresh), "duplicates": dupes, "problems": problems[:20], "saved": not b.preview, "sample": fresh[:3]}


class LinkIn(BaseModel):
    target: str = Field(max_length=800)
    post_ref: str = Field(default="", max_length=200)
    draft_id: int | None = None
    source: str = Field(default="linkedin", max_length=60)
    medium: str = Field(default="social", max_length=60)
    campaign: str = Field(min_length=1, max_length=80)


@router.post("/links", summary="Make a tracked short link. The target host must be on the allow list.")
def make_link(b: LinkIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    target = _rule(attribution.make_target, b.target, ctx.settings.allow_hosts(), b.source, b.medium, b.campaign, "", ctx.settings.allow_http_local_targets)
    same = s.scalars(select(Link).where(Link.target == target, Link.post_ref == b.post_ref, Link.draft_id == b.draft_id, Link.campaign == attribution.slug(b.campaign), Link.source == attribution.slug(b.source), Link.medium == attribution.slug(b.medium))).first()
    if same is not None:  # pressing the button twice must not make two links that split the clicks
        return {"id": same.id, "code": same.code, "short_url": f"{ctx.settings.public_base_url.rstrip('/')}/r/{same.code}", "short_path": f"/r/{same.code}", "target": same.target, "existing": True}
    code = _rule(attribution.new_code, set(s.scalars(select(Link.code))))
    row = Link(code=code, target=target, post_ref=b.post_ref, draft_id=b.draft_id, source=attribution.slug(b.source), medium=attribution.slug(b.medium), campaign=attribution.slug(b.campaign))
    s.add(row)
    s.flush()
    record_audit(s, u["user"], "link.created", f"link:{row.id}", {"code": code})
    return {"id": row.id, "code": code, "short_url": f"{ctx.settings.public_base_url.rstrip('/')}/r/{code}", "short_path": f"/r/{code}", "target": target, "existing": False}


class ExperimentIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    metric: str = Field(default="link clicks", max_length=60)
    a_label: str = Field(default="A", max_length=60)
    b_label: str = Field(default="B", max_length=60)


@router.post("/experiments", summary="Start an A/B experiment")
def make_experiment(b: ExperimentIn, s: Session = Depends(db), u: dict = Depends(writer)):
    row = Experiment(name=b.name, metric=b.metric, a_label=b.a_label, b_label=b.b_label)
    s.add(row)
    s.flush()
    return {"id": row.id}


class CountsIn(BaseModel):
    a_n: int = Field(ge=0, le=10**9)
    a_hits: int = Field(ge=0, le=10**9)
    b_n: int = Field(ge=0, le=10**9)
    b_hits: int = Field(ge=0, le=10**9)


@router.put("/experiments/{exp_id}", summary="Update the counts of an experiment")
def update_experiment(exp_id: int, b: CountsIn, s: Session = Depends(db), u: dict = Depends(writer)):
    e = s.get(Experiment, exp_id)
    if e is None:
        raise HTTPException(404, "No such experiment.")
    if b.a_hits > b.a_n or b.b_hits > b.b_n:
        raise HTTPException(400, "Hits cannot be more than views.")
    e.a_n, e.a_hits, e.b_n, e.b_hits = b.a_n, b.a_hits, b.b_n, b.b_hits
    return {"ok": True}
