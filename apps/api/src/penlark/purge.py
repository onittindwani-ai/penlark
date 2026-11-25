"""Taking things out for good: a note, a writing sample, a draft, a voice, imported post numbers.

What a person asked to remove must not live on somewhere else in the database. A note is quoted word for word in the ideas found from it; a sample is quoted in the
example sentences of every voice profile built after it was added; a draft has variants, calendar rows, an approval and maybe a file that was exported. Each function here
removes the thing and every copy of its words that the app itself made, and says what it could not touch (a draft that quotes a deleted note keeps its own words: they
are the person's text now). The audit log never held any text, only ids and counts, so it stays as it is.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from penlark import service
from penlark.models import Author, Draft, Idea, Link, Note, Performance, Sample, Schedule, Variant, VoiceProfile
from sendora_core.audit import record_audit
from sendora_core.models import Approval

SENT_DRAFT = {"sending", "send_unknown", "published"}
OPEN_DRAFT = {"pending_approval", "approved", "scheduled"}


class Refused(ValueError):
    """The removal would break a safeguard. The message is for a person."""


def draft_blocker(s: Session, d: Draft) -> str | None:
    """Why this draft cannot be removed, or None. A draft that was sent (or may have been) keeps its row: the sent record on it is the only thing that stops a second send."""
    if d.status in SENT_DRAFT or s.scalar(select(Schedule.id).where(Schedule.draft_id == d.id, Schedule.status.in_(("sent", "unclear", "sending")))):
        return f"The draft \"{d.title[:60]}\" was sent to a scheduling tool, or may have been. It stays as the record that stops a second send. Remove the post in the tool yourself."
    return None


def _scrub_approvals(s: Session, draft_id: int) -> None:
    for a in s.scalars(select(Approval).where(Approval.action == "draft.approve")):
        if int((a.payload or {}).get("draft_id", 0) or 0) == draft_id:
            a.summary = "Approve a draft that was later deleted"  # the title was the person's words
            if a.status == "pending":
                a.status, a.decided_by, a.decision_note = "rejected", "system", "The draft was deleted."


def delete_draft(s: Session, ctx, d: Draft, actor: str) -> dict:
    why = draft_blocker(s, d)
    if why:
        raise Refused(why)
    draft_id = d.id
    _scrub_approvals(s, draft_id)
    files = 0
    out = Path(ctx.settings.export_dir)
    if out.is_dir():
        for f in out.glob(f"draft-{int(draft_id)}-*.txt"):  # the file an export wrote: the same words, outside the database
            f.unlink(missing_ok=True)
            files += 1
    s.execute(delete(Variant).where(Variant.draft_id == draft_id))
    s.execute(delete(Schedule).where(Schedule.draft_id == draft_id))
    s.execute(update(Link).where(Link.draft_id == draft_id).values(draft_id=None))
    s.execute(update(Performance).where(Performance.draft_id == draft_id).values(draft_id=None))
    s.delete(d)
    s.flush()
    record_audit(s, actor, "draft.deleted", f"draft:{draft_id}", {"files_removed": files})
    return {"ok": True, "files_removed": files}


def delete_note(s: Session, note: Note, actor: str) -> dict:
    note_id = note.id
    quotes: list[str] = []
    removed = kept = 0
    for idea in list(s.scalars(select(Idea))):
        if note_id not in (idea.note_ids or []) and not any(e.get("note_id") == note_id for e in idea.evidence or []):
            continue
        quotes += [str(e.get("quote", "")) for e in idea.evidence or [] if e.get("note_id") == note_id]
        left = [e for e in idea.evidence or [] if e.get("note_id") != note_id]
        if left:
            idea.evidence, idea.note_ids = left, [n for n in idea.note_ids or [] if n != note_id]
            kept += 1
        else:
            s.execute(update(Draft).where(Draft.idea_id == idea.id).values(idea_id=None))
            s.delete(idea)
            removed += 1
    unlinked: list[int] = []
    for d in s.scalars(select(Draft)):
        cited = note_id in (d.source_note_ids or []) or note_id in {int(v) for v in (d.claim_links or {}).values()}
        if not cited:
            continue
        d.source_note_ids = [n for n in d.source_note_ids or [] if n != note_id]
        d.claim_links = {k: v for k, v in (d.claim_links or {}).items() if int(v) != note_id}
        if d.status in OPEN_DRAFT:  # the support of its claims changed: it has to be checked and approved again
            if d.status == "pending_approval":
                service.withdraw_approval(s, d, actor, "A note this draft was written from was deleted.")
            d.status = "draft"
        unlinked.append(d.id)
    quoting = sorted({d.id for d in s.scalars(select(Draft)) for q in quotes if len(q) >= 20 and q in d.text})
    s.delete(note)
    s.flush()
    record_audit(s, actor, "note.deleted", f"note:{note_id}", {"ideas_removed": removed, "ideas_trimmed": kept, "drafts_unlinked": len(unlinked)})
    return {"ok": True, "ideas_removed": removed, "ideas_trimmed": kept, "drafts_unlinked": unlinked, "drafts_still_quoting_it": quoting}


def delete_sample(s: Session, sample: Sample, actor: str) -> dict:
    """The sentences of a sample are copied into the example sentences and the favourite phrases of every voice profile built after it was added, so those versions go too,
    and a new version is built from the samples that are left (with the plain guide: asking a model is a separate step the person chooses)."""
    author_id, sample_id, added = sample.author_id, sample.id, service._aware(sample.created_at)
    s.delete(sample)
    s.flush()
    stale = [p for p in s.scalars(select(VoiceProfile).where(VoiceProfile.author_id == author_id)) if service._aware(p.created_at) >= added]
    locked = any(p.locked for p in stale)
    for p in stale:
        s.delete(p)
    s.flush()
    rebuilt = None
    if s.scalar(select(Sample.id).where(Sample.author_id == author_id).limit(1)) is not None:
        rebuilt = service.build_profile(s, author_id, actor).version
    record_audit(s, actor, "sample.removed", f"sample:{sample_id}", {"profiles_removed": len(stale), "rebuilt_version": rebuilt})
    return {"ok": True, "profiles_removed": len(stale), "rebuilt_version": rebuilt, "locked_profile_removed": locked}


def delete_author(s: Session, ctx, author: Author, actor: str) -> dict:
    drafts = list(s.scalars(select(Draft).where(Draft.author_id == author.id)))
    for d in drafts:
        why = draft_blocker(s, d)
        if why:
            raise Refused(f"This voice cannot be removed yet. {why}")
    files = sum(delete_draft(s, ctx, d, actor)["files_removed"] for d in drafts)
    n_samples = s.execute(delete(Sample).where(Sample.author_id == author.id)).rowcount
    n_profiles = s.execute(delete(VoiceProfile).where(VoiceProfile.author_id == author.id)).rowcount
    author_id = author.id
    s.delete(author)
    s.flush()
    record_audit(s, actor, "author.deleted", f"author:{author_id}", {"drafts": len(drafts), "samples": n_samples, "profiles": n_profiles})
    return {"ok": True, "drafts_removed": len(drafts), "samples_removed": n_samples, "profiles_removed": n_profiles, "files_removed": files}


def delete_performance(s: Session, ids: list[int] | None, actor: str) -> dict:
    q = delete(Performance) if ids is None else delete(Performance).where(Performance.id.in_(ids))
    n = s.execute(q).rowcount
    record_audit(s, actor, "performance.deleted", None, {"rows": n, "all": ids is None})
    return {"ok": True, "rows": n}
