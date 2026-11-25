from __future__ import annotations

import copy
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from penlark import attribution, ingest, learning, safe_regex, service
from penlark.adapters.schedulers import UnclearAnswer
from penlark.api.bodies import Body
from penlark.api.deps import db, db_read, get_ctx, owner, writer
from penlark.api.routes_public import read_bounded
from penlark.api.serializers import draft_dict
from penlark.api.types import MAX_LIST, Id, PathId, QueryId
from penlark.context import Ctx
from penlark.match import match
from penlark.models import Author, Draft, Experiment, HouseRule, Idea, Link, Note, Performance, Sample, Schedule, Variant, VoiceProfile
from sendora_core.approvals import request_approval
from sendora_core.audit import record_audit
from sendora_core.jobs import enqueue
from sendora_core.models import Job
from sendora_core.adapters import AdapterError
from sendora_core.safety import SafetyError

router = APIRouter(prefix="/api", tags=["write"])
PLATFORM_PATTERN = "^(linkedin|x|instagram|facebook|threads|youtube|newsletter|email)$"
UNPLAN_REFUSED = {
    "sent": "This draft was already sent to the scheduling tool, so it stays on the calendar as a record. To take the post down, remove it in the scheduling tool yourself; sending it again from here would make a second post.",
    "sending": "This draft is being sent right now. Wait for the answer.",
    "unclear": "A send to the scheduling tool gave no clear answer. Check the tool and say whether the post was made first.",
    "exported": "This draft was saved to a file, so it stays on the calendar as a record of the export.",
}
LOCKED_STATUSES = {"exported", "published", "sending", "send_unknown"}  # the words can no longer change


def _rule(fn, *a, **k):
    try:
        return fn(*a, **k)
    except (service.RuleError, ingest.IngestError, learning.ImportError_, attribution.LinkError) as exc:
        raise HTTPException(400, str(exc)) from exc


class MatchIn(Body):
    author_id: Id
    text: str = Field(max_length=30000)
    source_note_ids: list[Id] = Field(default_factory=list, max_length=MAX_LIST)
    claim_links: dict[str, Id] = Field(default_factory=dict, max_length=MAX_LIST)


@router.post("/match", summary="Live voice match and house rule check of any text. Writes nothing.")
def live_match(b: MatchIn, s: Session = Depends(db_read, scope="function"), ctx: Ctx = Depends(get_ctx)):
    return service.evaluate(s, ctx.settings, b.author_id, b.text, b.source_note_ids, b.claim_links)


class AuthorIn(Body):
    name: str = Field(min_length=2, max_length=120)
    about: str = Field(default="", max_length=2000)


@router.post("/authors", summary="Add a voice: the person or brand whose writing the drafts should sound like")
def add_author(b: AuthorIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    name = b.name.strip()
    if len(name) < 2:
        raise HTTPException(400, "Type at least two characters for the name.")
    if any(a.strip().lower() == name.lower() for a in s.scalars(select(Author.name))):
        raise HTTPException(409, "There is already a voice with that name.")
    row = Author(slug=service.unique_author_slug(s, name), name=name, about=b.about.strip())
    s.add(row)
    s.flush()
    record_audit(s, u["user"], "author.created", f"author:{row.id}", {})
    return {"id": row.id, "slug": row.slug, "name": row.name}


class SampleIn(Body):
    author_id: Id
    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=20, max_length=200000)
    kind: str = "text"  # text, markdown, transcript


@router.post("/samples", summary="Add a pasted writing sample, transcript or markdown")
def add_sample(b: SampleIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    item = _rule(lambda: ingest.from_transcript(b.text, b.title) if b.kind == "transcript" else ingest.from_markdown(b.text, b.title) if b.kind == "markdown" else ingest.from_text(b.text, b.title))
    if s.get(Author, b.author_id) is None:
        raise HTTPException(404, "No such voice.")
    if service.sample_digest(item.text) in service.sample_digests(s, b.author_id):
        raise HTTPException(409, "That text is already in this voice's library.")
    row = Sample(author_id=b.author_id, title=item.title[:200], kind=item.kind, text=item.text, source="pasted")
    s.add(row)
    s.flush()
    record_audit(s, u["user"], "sample.added", f"sample:{row.id}", {"words": len(item.text.split())})
    return {"id": row.id, "title": row.title}


@router.post("/samples/upload", summary="Upload a file: text, markdown, PDF, transcript, LinkedIn Shares.csv or X tweets.js")
async def upload_sample(request: Request, author_id: QueryId, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    name = (request.headers.get("x-filename") or "upload.txt")[:150].replace("\x00", "")
    # The file is read and parsed before the database is touched: on SQLite the first query of a request that can write takes the write lock, and a slow upload must not hold it.
    data = await read_bounded(request, ingest.MAX_BYTES, "That file is larger than 8 MB.")  # refused while it arrives, never held whole
    items = await run_in_threadpool(_rule, ingest.detect, name, data)  # reading a file can take a while: not on the thread that serves everyone else
    # Everything that asks the database (and can wait for its lock) or hashes the library runs on a worker thread, never on the thread that serves everyone else.
    return await run_in_threadpool(_store_upload, s, author_id, name, items, u["user"])


def _store_upload(s: Session, author_id: int, name: str, items: list, user: str) -> dict:
    if s.get(Author, author_id) is None:
        raise HTTPException(404, "No such voice.")
    known, fresh = service.sample_digests(s, author_id), []
    for it in items:  # the set grows as items are taken, so the same text twice in one file counts once
        key = service.sample_digest(it.text)
        if key not in known:
            known.add(key)
            fresh.append(it)
    for it in fresh:
        s.add(Sample(author_id=author_id, title=it.title[:200], kind=it.kind, text=it.text, source=f"file {name}"[:200]))
        s.flush()
    record_audit(s, user, "sample.uploaded", name, {"items": len(fresh), "skipped": len(items) - len(fresh)})
    return {"added": len(fresh), "skipped": len(items) - len(fresh)}


class BuildIn(Body):
    author_id: Id


@router.post("/profile/build", summary="Measure the samples and make a new profile version (not locked)")
def build(b: BuildIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    p = _rule(service.build_profile, s, b.author_id, u["user"], ctx)
    return {"id": p.id, "version": p.version, "diff": p.diff}


class GuideIn(Body):
    guide: str = Field(max_length=6000)


@router.put("/profile/{profile_id}/guide", summary="Edit the guide. A locked profile cannot be edited, build a new version instead.")
def edit_guide(profile_id: PathId, b: GuideIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    p = s.get(VoiceProfile, profile_id)
    if p is None:
        raise HTTPException(404, "No such profile.")
    if p.locked:
        raise HTTPException(409, "This version is locked. Build a new version to change the guide.")
    p.guide, p.guide_source = b.guide, "edited by a person"
    record_audit(s, u["user"], "profile.guide_edited", f"profile:{p.id}", {})
    return {"ok": True}


@router.post("/profile/{profile_id}/lock", summary="Lock a profile so scores use a fixed voice")
def lock(profile_id: PathId, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    p = s.get(VoiceProfile, profile_id)
    if p is None:
        raise HTTPException(404, "No such profile.")
    p.locked, p.locked_by = True, u["user"]
    record_audit(s, u["user"], "profile.locked", f"profile:{p.id}", {"version": p.version})
    return {"ok": True}


class NoteIn(Body):
    kind: str = Field(pattern="^(call|comment|email|note|fact)$")
    who: str = Field(default="", max_length=200)
    text: str = Field(min_length=8, max_length=20000)
    occurred_on: str = Field(default="", max_length=10)


@router.post("/notes", summary="Add a call, comment, email, note or a founder fact")
def add_note(b: NoteIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    if len(b.text.strip()) < 8:
        raise HTTPException(400, "Write at least a short sentence.")
    row = Note(kind=b.kind, who=b.who.strip(), text=b.text.strip(), occurred_on=b.occurred_on)
    s.add(row)
    s.flush()
    record_audit(s, u["user"], "note.added", f"note:{row.id}", {"kind": b.kind})
    return {"id": row.id}


@router.post("/ideas/refresh", summary="Find ideas again from the newest notes. A real install queues a job for the worker; the offline demo has no worker and answers at once.")
def refresh(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    if ctx.settings.demo_shortcuts:
        n = service.load_ideas(s, service.recent_notes(s), ctx)
        record_audit(s, u["user"], "ideas.refreshed", None, {"ideas": n})
        return {"queued": False, "ideas": n}
    job = s.scalars(select(Job).where(Job.kind == "ideas", Job.status.in_(("queued", "running"))).order_by(Job.id.desc())).first()
    if job is None:  # pressing the button again while one is waiting must not stack up more work
        job = enqueue(s, "ideas")
        record_audit(s, u["user"], "ideas.refresh_requested", f"job:{job.id}", {})
    return {"queued": True, "job_id": job.id, "ideas": 0}


@router.post("/ideas/{idea_id}/drop", summary="Drop an idea")
def drop(idea_id: PathId, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    i = s.get(Idea, idea_id)
    if i is None:
        raise HTTPException(404, "No such idea.")
    i.status = "dropped"
    record_audit(s, u["user"], "idea.dropped", f"idea:{idea_id}", {})
    return {"ok": True}


class DraftFromIdea(Body):
    author_id: Id
    kind: str = Field(default="post", pattern="^(post|script|email|newsletter)$")


@router.post("/ideas/{idea_id}/draft", summary="Write a draft from an idea in a chosen voice (offline stand in)")
def draft_from_idea(idea_id: PathId, b: DraftFromIdea, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = _rule(service.create_drafts_from_idea, s, ctx, idea_id, b.author_id, b.kind, u["user"])
    return {"id": d.id}


class DraftIn(Body):
    text: str = Field(max_length=30000)
    author_id: Id | None = None
    title: str | None = Field(default=None, max_length=200)
    source_note_ids: list[Id] | None = Field(default=None, max_length=MAX_LIST)
    claim_links: dict[str, Id] | None = Field(default=None, max_length=MAX_LIST)


@router.put("/drafts/{draft_id}", summary="Edit a draft. Editing an approved draft sends it back to draft.")
def edit_draft(draft_id: PathId, b: DraftIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = service.lock_draft(s, draft_id, ctx)  # held until this request ends, so a decision cannot run through the edit
    if d is None:
        raise HTTPException(404, "No such draft.")
    if d.status in LOCKED_STATUSES:
        raise HTTPException(409, "This draft was already exported or sent, or is waiting for you to say whether a send went through. Copy it into a new draft to change it.")
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
    if changed:
        record_audit(s, u["user"], "draft.edited", f"draft:{d.id}", {"chars": len(d.text), "sha256": service.text_digest(d.text)})
    d.updated_at = ctx.now(s)
    return draft_dict(d)


@router.post("/drafts/{draft_id}/variants/{variant_id}/use", summary="Replace the draft text with a variant")
def use_variant(draft_id: PathId, variant_id: PathId, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d, v = service.lock_draft(s, draft_id, ctx), s.get(Variant, variant_id)
    if d is None or v is None or v.draft_id != d.id:
        raise HTTPException(404, "No such variant.")
    if d.status in LOCKED_STATUSES:
        raise HTTPException(409, "This draft was already exported or sent, or is waiting for you to say whether a send went through. Copy it into a new draft to change it.")
    if d.status == "pending_approval":
        service.withdraw_approval(s, d, u["user"], "The draft was changed after it was sent for approval.")
    d.text, d.status, d.updated_at = v.text, "draft", ctx.now(s)
    record_audit(s, u["user"], "draft.edited", f"draft:{d.id}", {"chars": len(d.text), "sha256": service.text_digest(d.text), "variant": v.id})
    return draft_dict(d)


@router.post("/drafts/{draft_id}/request-approval", summary="Ask a second person to approve this draft")
def request(draft_id: PathId, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = service.lock_draft(s, draft_id, ctx)
    if d is None:
        raise HTTPException(404, "No such draft.")
    # An approved draft whose approval no longer matches its words (an approval from before approvals were tied to the text) may be asked for again.
    stale = d.status in {"approved", "scheduled"} and service.binding_problem(s, d) is not None
    if d.status not in {"draft", "rejected"} and not stale:
        raise HTTPException(409, "This draft is already waiting or approved.")
    ev = service.evaluate(s, ctx.settings, d.author_id, d.text, d.source_note_ids, d.claim_links)
    why = service.readiness_problem(ev, ctx.settings.min_voice_match)
    if why:
        raise HTTPException(409, why)
    a = request_approval(s, "draft.approve", f"Approve draft: {d.title}", {"draft_id": d.id, "match": ev["match"]["score"], "text_sha256": service.text_digest(d.text)}, "medium", u["user"])
    d.status, d.approval_id = "pending_approval", a.id
    return {"approval_id": a.id}


class ScheduleIn(Body):
    platform: str = Field(default="linkedin", pattern=PLATFORM_PATTERN)
    run_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/drafts/{draft_id}/schedule", summary="Put an approved draft on the calendar (a plan, nothing is sent)")
def schedule(draft_id: PathId, b: ScheduleIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = service.lock_draft(s, draft_id, ctx)  # held until this request ends, so a send or an edit cannot run through it
    if d is None:
        raise HTTPException(404, "No such draft.")
    if d.status not in {"approved", "scheduled"}:
        raise HTTPException(409, "Only an approved draft can go on the calendar. Ask a second person to approve it first.")
    if (why := service.binding_problem(s, d)) is not None:
        raise HTTPException(409, why)
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


class MoveIn(Body):
    run_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.put("/schedule/{schedule_id}", summary="Move a planned item to another day (drag on the calendar)")
def move(schedule_id: PathId, b: MoveIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    row = s.get(Schedule, schedule_id)
    if row is None:
        raise HTTPException(404, "No such item.")
    service.lock_draft(s, row.draft_id, ctx)
    row = s.get(Schedule, schedule_id, populate_existing=True)  # read again now that the draft is held
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


@router.delete("/schedule/{schedule_id}", summary="Take a planned item off the calendar. Only a plan can be removed: a sent or exported item is a record.")
def unschedule(schedule_id: PathId, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    row = s.get(Schedule, schedule_id)
    if row is None:
        raise HTTPException(404, "No such item.")
    d = service.lock_draft(s, row.draft_id, ctx)
    row = s.get(Schedule, schedule_id, populate_existing=True)  # read again now that the draft is held
    if row is None:
        raise HTTPException(404, "No such item.")
    if row.status != "planned":
        # A sent row is the only thing that stops a second send of the same words: taking it away would put the draft back to approved and a second click would post it twice.
        raise HTTPException(409, UNPLAN_REFUSED.get(row.status, "Only a planned item can be taken off the calendar."))
    s.delete(row)
    s.flush()
    if d and d.status == "scheduled" and not s.scalar(select(Schedule.id).where(Schedule.draft_id == d.id)):
        d.status = "approved"
    record_audit(s, u["user"], "schedule.removed", f"schedule:{schedule_id}", {"draft": row.draft_id})
    return {"ok": True}


class ExportIn(Body):
    platform: str | None = Field(default=None, pattern=PLATFORM_PATTERN)


@router.post("/drafts/{draft_id}/export", summary="Save an approved draft to a file to copy and post yourself (the default way out)")
def export(draft_id: PathId, b: ExportIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = service.lock_draft(s, draft_id, ctx)
    if d is None:
        raise HTTPException(404, "No such draft.")
    if ctx.effective(s).kill_switch:  # the owner's switch in the app, read from the database now, not the environment: nothing is written outside the database while it is on
        raise HTTPException(409, "The kill switch is on, so nothing was exported. Turn it off in settings to continue.")
    if d.status not in {"approved", "scheduled"}:
        raise HTTPException(409, "Only an approved draft can be exported. Ask a second person to approve it first.")
    if (why := service.binding_problem(s, d)) is not None:
        raise HTTPException(409, why)
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


class SendIn(Body):
    platform: str = Field(default="linkedin", pattern=PLATFORM_PATTERN)
    channel_id: str = Field(min_length=1, max_length=120)
    confirm: bool = False
    as_draft: bool = True
    run_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


def _sending_row(s: Session, draft_id: int) -> Schedule | None:
    return s.scalars(select(Schedule).where(Schedule.draft_id == draft_id, Schedule.status == "sending").order_by(Schedule.id.desc())).first()


def _stop_send(s: Session, draft_id: int, before: str, user: str, why: str, code: int = 409) -> HTTPException:
    """Put the draft back where it was, keep a record that the send did not go through (committed now, before the error rolls the request back), and return the error."""
    d = service.lock_draft(s, draft_id)
    d.status = before
    if (row := _sending_row(s, draft_id)) is not None:
        s.delete(row)  # the calendar row written when the send started: nothing was posted, so it goes
    record_audit(s, user, "draft.send_failed", f"draft:{draft_id}", {"reason": why[:200]})
    s.commit()
    return HTTPException(code, why)


# A failure that happens before anything reached the vendor, or an answer that clearly says "no": the post was not made, so the draft may go back to approved.
_NEVER_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.UnsupportedProtocol, httpx.LocalProtocolError, httpx.InvalidURL)


def _clearly_not_sent(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return 400 <= exc.response.status_code < 500 and exc.response.status_code != 408  # a refusal with a meaning; a 408 timeout says nothing about the post
    return isinstance(exc, _NEVER_SENT)


def _unclear_send(s: Session, draft_id: int, user: str, adapter: str, platform: str, run_on: str, reason: str = "") -> HTTPException:
    """A timeout, a server error or an answer nobody can read: the post may exist. The draft stays out of reach (no second send, no edit) until a person checks the tool and says which it was."""
    d = service.lock_draft(s, draft_id)
    service.hold_unclear_send(s, d, user, adapter, platform, run_on, reason)
    why = f"{adapter} did not give a clear answer. The post may or may not have been made. Check {adapter} first, then tell the app: it was posted, or it was not."
    s.commit()
    return HTTPException(502, why + (f" ({reason})" if reason else ""))


@router.post("/drafts/{draft_id}/send", summary="Send an approved draft to Postiz, Buffer or Metricool. Needs live mode, an approval and confirm.")
def send(draft_id: PathId, b: SendIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = service.lock_draft(s, draft_id, ctx)
    if d is None:
        raise HTTPException(404, "No such draft.")
    if d.status == "sending":  # the first send is still out at the tool: this request must not touch its calendar row
        raise HTTPException(409, "This draft is being sent right now. Wait for the answer.")
    if d.status == "send_unknown":
        raise HTTPException(409, "The last send gave no clear answer. Check the scheduling tool, then say whether the post was made (It was posted, or It was not posted) before anything else.")
    sched = ctx.scheduler
    if not hasattr(sched, "send") or sched.name in {"export", "seed"}:
        raise HTTPException(409, "The file export never sends. Choose Postiz, Buffer or Metricool in the settings.")
    if b.run_on and sched.name == "buffer":  # Penlark has no verified way to give Buffer a time, so a date would be dropped without a word: say so instead
        raise HTTPException(400, "Buffer adds the post to its own queue or saves a draft, and Penlark cannot give it a date. Leave the date empty and choose the time in Buffer.")
    try:
        day = datetime.strptime(b.run_on, "%Y-%m-%d").date() if b.run_on else ctx.today(s) + timedelta(days=1)
    except ValueError as exc:
        raise HTTPException(400, "That is not a real date.") from exc
    when = datetime.combine(day, time(ctx.settings.send_hour), tzinfo=ZoneInfo(ctx.settings.timezone)).astimezone(timezone.utc)  # the send hour in the owner's timezone, not midnight UTC
    if when < ctx.now(s) - timedelta(minutes=1):
        raise HTTPException(400, "That date and hour are in the past, so the scheduling tool would post at once or refuse. Pick a later date.")
    if d.status in {"approved", "scheduled"} and s.scalar(select(Schedule.id).where(Schedule.draft_id == d.id, Schedule.status == "sent")):
        raise HTTPException(409, "This draft was already sent to the scheduling tool. Open it there; sending it again would make a second post.")
    if d.status in {"approved", "scheduled"} and (why := service.binding_problem(s, d)) is not None:
        raise HTTPException(409, why)
    before, text, run_on = d.status, d.text, when.date().isoformat()
    # Claim the draft in one conditional step: a second request that arrives while this one is out at the vendor finds it no longer approved and stops.
    claimed = s.execute(update(Draft).where(Draft.id == d.id, Draft.status.in_(("approved", "scheduled"))).values(status="sending", updated_at=ctx.now(s))) if before in {"approved", "scheduled"} else None
    if claimed is not None and claimed.rowcount != 1:
        raise HTTPException(409, "This draft is being sent or was just sent.")
    if claimed is not None:  # the calendar row of this send: it becomes "sent" or "unclear", or goes if the tool clearly said no
        s.add(Schedule(draft_id=d.id, platform=b.platform, run_on=run_on, status="sending", adapter=sched.name, detail=f"Being sent to {sched.name}."))
    eff = ctx.effective(s)  # the kill switch and the draft mode, read from the database now
    once = copy.copy(sched)  # a copy for this request: the shared adapter is never changed, so another request cannot borrow these settings
    once.s = eff
    s.commit()  # the claim is visible to every other request from now on, and still there if this process stops half way. The write lock is let go here: nothing below may hold it while the vendor answers.
    try:
        res = once.send(text, b.platform, when, b.channel_id, approved=before in {"approved", "scheduled"}, confirm=b.confirm, as_draft=b.as_draft)
    except (AdapterError, SafetyError) as exc:
        raise _stop_send(s, draft_id, before, u["user"], str(exc)) from exc
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        if _clearly_not_sent(exc):  # it never left, or the tool said no with a reason: nothing was posted
            raise _stop_send(s, draft_id, before, u["user"], f"{sched.name} did not take the post ({type(exc).__name__}). Nothing was posted.", 502) from exc
        raise _unclear_send(s, draft_id, u["user"], sched.name, b.platform, run_on, str(exc) if isinstance(exc, UnclearAnswer) else "") from exc  # the post may exist: keep the draft held
    d = service.lock_draft(s, draft_id)
    row = _sending_row(s, draft_id)
    if row is None:
        row = Schedule(draft_id=draft_id, platform=b.platform, run_on=run_on, adapter=sched.name)
        s.add(row)
    row.status, row.external_id, row.detail = "sent", res["external_id"][:120], res["detail"][:300]
    d.status = "published" if not b.as_draft else "scheduled"
    record_audit(s, u["user"], "draft.sent", f"draft:{draft_id}", {"adapter": sched.name, "as_draft": b.as_draft})
    return res


class OutcomeIn(Body):
    posted: bool
    external_id: str = Field(default="", max_length=120)  # the column that keeps it holds 120


@router.post("/drafts/{draft_id}/send-outcome", summary="After a send with no clear answer: say whether the post was made, once you have looked in the scheduling tool")
def send_outcome(draft_id: PathId, b: OutcomeIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    d = service.lock_draft(s, draft_id, ctx)  # a send left behind for over half an hour becomes "send_unknown" here too
    if d is None:
        raise HTTPException(404, "No such draft.")
    if d.status != "send_unknown":
        raise HTTPException(409, "This draft is not waiting for that answer.")
    row = s.scalars(select(Schedule).where(Schedule.draft_id == d.id, Schedule.status == "unclear").order_by(Schedule.id.desc())).first()
    if b.posted:  # it exists at the tool: the draft is handed over, and it can never be sent a second time from here
        if row is None:
            last = s.scalars(select(Schedule).where(Schedule.draft_id == d.id).order_by(Schedule.id.desc())).first()  # the platform of the send, not a guess
            row = Schedule(draft_id=d.id, platform=last.platform if last else "linkedin", run_on=ctx.today(s).isoformat(), adapter=ctx.scheduler.name)
            s.add(row)
        row.status, row.external_id, row.detail = "sent", b.external_id.strip(), f"A person confirmed the post exists in {ctx.scheduler.name}."
        d.status = "scheduled"
    else:
        if row is not None:
            s.delete(row)
        d.status = "approved"
    d.updated_at = ctx.now(s)
    record_audit(s, u["user"], "draft.send_posted" if b.posted else "draft.send_not_posted", f"draft:{d.id}", {"adapter": ctx.scheduler.name})
    return {"status": d.status}


class RuleIn(Body):
    kind: str = Field(pattern="^(phrase|pattern)$")
    value: str = Field(min_length=2, max_length=300)
    note: str = Field(default="", max_length=300)


@router.post("/rules", summary="Add a banned phrase or pattern")
def add_rule(b: RuleIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    value = b.value.strip()
    if b.kind == "pattern" and (why := safe_regex.problem(value)):  # a pattern that could freeze the app on a long text is refused here and never stored
        raise HTTPException(400, why)
    if len(value) < 2:
        raise HTTPException(400, "Type at least two characters.")
    if any(r.value.strip().lower() == value.lower() and r.kind == b.kind for r in s.scalars(select(HouseRule))):
        raise HTTPException(409, "That rule is already in the list." )
    row = HouseRule(kind=b.kind, value=value, note=b.note)
    s.add(row)
    s.flush()
    record_audit(s, u["user"], "rule.added", f"rule:{row.id}", {"kind": b.kind})
    return {"id": row.id}


class RuleToggle(Body):
    enabled: bool


@router.put("/rules/{rule_id}", summary="Turn a rule on or off")
def toggle_rule(rule_id: PathId, b: RuleToggle, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    r = s.get(HouseRule, rule_id)
    if r is None:
        raise HTTPException(404, "No such rule.")
    r.enabled = b.enabled
    record_audit(s, u["user"], "rule.toggled", f"rule:{rule_id}", {"enabled": b.enabled})
    return {"ok": True}


@router.delete("/rules/{rule_id}", summary="Delete your own rule (built in rules can only be turned off)")
def delete_rule(rule_id: PathId, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    r = s.get(HouseRule, rule_id)
    if r is None:
        raise HTTPException(404, "No such rule.")
    if r.builtin:
        raise HTTPException(409, "Built in rules can be turned off, not deleted.")
    s.delete(r)
    record_audit(s, u["user"], "rule.deleted", f"rule:{rule_id}", {"kind": r.kind})
    return {"ok": True}


class ImportIn(Body):
    csv: str = Field(max_length=5_000_000)
    mapping: dict[str, str] | None = None
    preview: bool = True


@router.post("/performance/import", summary="Import post numbers from CSV. With preview true nothing is saved.")
def import_csv(b: ImportIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    import csv, io

    try:
        headers = next(csv.reader(io.StringIO(b.csv)), [])
    except csv.Error:
        return {"ok": False, "headers": [], "suggested": {}, "message": learning.CSV_CELL_TOO_LONG, "rows": 0, "problems": []}
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


class LinkIn(Body):
    target: str = Field(max_length=800)
    post_ref: str = Field(default="", max_length=200)
    draft_id: Id | None = None
    source: str = Field(default="linkedin", max_length=60)
    medium: str = Field(default="social", max_length=60)
    campaign: str = Field(min_length=1, max_length=80)


@router.post("/links", summary="Make a tracked short link. The target host must be on the allow list.")
def make_link(b: LinkIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    if attribution.parse_address(b.target) is None:  # `https://[x` is not an address at all: a clear refusal, never a crash
        raise HTTPException(422, "That is not a web address. Check the square brackets and any full width punctuation, then try again.")
    target = _rule(attribution.make_target, b.target, ctx.settings.allow_hosts(), b.source, b.medium, b.campaign, "", ctx.settings.allow_http_local_targets)
    if len(target) > 1000:  # the stored address (with the tracking words added) must fit its column
        raise HTTPException(400, "That address is too long once the tracking words are added. Use a shorter address, or shorter campaign, source and medium names.")
    same = s.scalars(select(Link).where(Link.target == target, Link.post_ref == b.post_ref, Link.draft_id == b.draft_id, Link.campaign == attribution.slug(b.campaign), Link.source == attribution.slug(b.source), Link.medium == attribution.slug(b.medium))).first()
    if same is not None:  # pressing the button twice must not make two links that split the clicks
        return {"id": same.id, "code": same.code, "short_url": f"{ctx.settings.public_base_url.rstrip('/')}/r/{same.code}", "short_path": f"/r/{same.code}", "target": same.target, "existing": True}
    code = _rule(attribution.new_code, set(s.scalars(select(Link.code))))
    row = Link(code=code, target=target, post_ref=b.post_ref, draft_id=b.draft_id, source=attribution.slug(b.source), medium=attribution.slug(b.medium), campaign=attribution.slug(b.campaign))
    s.add(row)
    s.flush()
    record_audit(s, u["user"], "link.created", f"link:{row.id}", {"code": code})
    return {"id": row.id, "code": code, "short_url": f"{ctx.settings.public_base_url.rstrip('/')}/r/{code}", "short_path": f"/r/{code}", "target": target, "existing": False}


class ExperimentIn(Body):
    name: str = Field(min_length=3, max_length=200)
    metric: str = Field(default="link clicks", max_length=60)
    a_label: str = Field(default="A", max_length=60)
    b_label: str = Field(default="B", max_length=60)


@router.post("/experiments", summary="Start an A/B experiment")
def make_experiment(b: ExperimentIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    row = Experiment(name=b.name, metric=b.metric, a_label=b.a_label, b_label=b.b_label)
    s.add(row)
    s.flush()
    record_audit(s, u["user"], "experiment.created", f"experiment:{row.id}", {})
    return {"id": row.id}


class CountsIn(Body):
    a_n: int = Field(ge=0, le=10**9)
    a_hits: int = Field(ge=0, le=10**9)
    b_n: int = Field(ge=0, le=10**9)
    b_hits: int = Field(ge=0, le=10**9)


@router.put("/experiments/{exp_id}", summary="Update the counts of an experiment")
def update_experiment(exp_id: PathId, b: CountsIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    e = s.get(Experiment, exp_id)
    if e is None:
        raise HTTPException(404, "No such experiment.")
    if b.a_hits > b.a_n or b.b_hits > b.b_n:
        raise HTTPException(400, "Hits cannot be more than views.")
    e.a_n, e.a_hits, e.b_n, e.b_hits = b.a_n, b.a_hits, b.b_n, b.b_hits
    record_audit(s, u["user"], "experiment.updated", f"experiment:{exp_id}", {})
    return {"ok": True}
