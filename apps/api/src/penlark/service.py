"""The orchestration layer: everything the API does with the database goes through here, so the rules live in one place."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from penlark import fingerprint, guide, house_rules, ideas, learning, model_tasks, writers
from penlark.match import match
from penlark.models import Author, Draft, Experiment, HouseRule, Idea, Link, Note, Performance, Sample, Schedule, Variant, VoiceProfile, Click, Conversion
from sendora_core.audit import record_audit
from sendora_core.events import record_event


class RuleError(ValueError):
    """A business rule refused the action. The message is for a person."""


def latest_profile(s: Session, author_id: int, locked_only: bool = False) -> VoiceProfile | None:
    q = select(VoiceProfile).where(VoiceProfile.author_id == author_id)
    if locked_only:
        q = q.where(VoiceProfile.locked.is_(True))
    return s.scalars(q.order_by(VoiceProfile.version.desc())).first()


def build_profile(s: Session, author_id: int, actor: str, ctx=None) -> VoiceProfile:
    author = s.get(Author, author_id)
    samples = list(s.scalars(select(Sample).where(Sample.author_id == author_id)))
    if not samples:
        raise RuleError("Add at least one writing sample first.")
    texts = [x.text for x in samples]
    stats = fingerprint.build_profile(texts)
    prev = latest_profile(s, author_id)
    name = author.name.replace(" (fictional)", "")
    text, source, note = guide.offline_guide(stats, name), "offline stand in", ""
    if ctx is not None and ctx.model_on() and ctx.settings.guide_writer == "model" and not (prev and prev.locked):
        res = model_tasks.write_guide(ctx.llm(s), stats, name, texts)
        text, source, note = res.value, res.writer, res.note  # type: ignore[assignment]
    # a locked guide is the person's own words: a rebuild keeps it and only refreshes the numbers if they ask for a new version
    row = VoiceProfile(author_id=author_id, version=(prev.version + 1) if prev else 1, stats=stats, guide=prev.guide if prev and prev.locked else text, guide_source="your edited guide" if prev and prev.locked else source,
                       locked=False, diff=guide.diff_profiles(prev.stats if prev else None, stats), examples=fingerprint.examples(texts), n_samples=len(samples))
    s.add(row)
    s.flush()
    record_audit(s, actor, "profile.built", f"profile:{row.id}", {"author": author_id, "version": row.version, "samples": len(samples), "guide_writer": source, **({"note": note} if note else {})})
    return row


def rules_for(s: Session, settings) -> house_rules.Rules:
    rows = list(s.scalars(select(HouseRule).where(HouseRule.enabled.is_(True))))
    r = house_rules.Rules([x.value for x in rows if x.kind == "phrase"], [(x.value, x.note or "Matches a banned pattern.") for x in rows if x.kind == "pattern"], settings.no_dashes, settings.max_reading_grade, None, settings.require_sources)
    return r


def notes_text(s: Session, ids: list[int]) -> dict[int, str]:
    return {n.id: n.text for n in s.scalars(select(Note).where(Note.id.in_(ids or [-1])))}


def evaluate(s: Session, settings, author_id: int, text: str, source_note_ids: list[int], claim_links: dict | None = None) -> dict:
    prof = latest_profile(s, author_id, locked_only=True) or latest_profile(s, author_id)
    m = match(text, prof.stats) if prof else {"score": 0, "confidence": "none", "dimensions": [], "weakest": [], "pull_down": [], "note": "Build a voice profile first."}
    checks = house_rules.check_all(text, rules_for(s, settings), notes_text(s, source_note_ids), {k: int(v) for k, v in (claim_links or {}).items()})
    brackets = [x for x in _brackets(text)]
    return {"match": m, "rules": checks, "placeholders": brackets, "profile_version": prof.version if prof else None, "profile_locked": bool(prof and prof.locked),
            "ready": bool(m["score"] >= settings.min_voice_match and checks["ok"] and not brackets)}


def readiness_problem(ev: dict, min_match: float) -> str | None:
    """Why a draft may not go to a second person, in plain words, or None when it may. One place, so asking and approving use the same bar."""
    if ev["placeholders"]:
        return "Fill the [BRACKETS] with your own real words first: " + ", ".join(ev["placeholders"][:4]) + "."
    if ev["rules"]["unsupported_claims"]:
        return "Needs a source or a founder fact: " + ev["rules"]["unsupported_claims"][0]["text"][:120]
    if ev["rules"]["style"]:
        return "A house rule is broken: " + ev["rules"]["style"][0]["message"]
    if ev["match"]["score"] < min_match:
        return f"The voice match is {ev['match']['score']}, under your minimum of {min_match}. Edit the draft closer to the author's voice first."
    return None


def withdraw_approval(s: Session, d: Draft, actor: str, why: str) -> None:
    """A draft that changed after it was sent for approval must not be approvable any more: the person would approve words they never saw."""
    from sendora_core.db import utcnow
    from sendora_core.models import Approval

    a = s.get(Approval, d.approval_id) if d.approval_id else None
    if a is not None and a.status == "pending":
        a.status, a.decided_by, a.decision_note, a.decided_at = "rejected", "system", why, utcnow()
        record_audit(s, "system", "approval.withdrawn", f"approval:{a.id}", {"draft": d.id, "why": why})


def _brackets(text: str) -> list[str]:
    import re

    return re.findall(r"\[[A-Z][A-Z0-9 ,'\-]{2,}[A-Z0-9\]]*\]", text)


def create_drafts_from_idea(s: Session, ctx, idea_id: int, author_id: int, kind: str, actor: str) -> Draft:
    idea = s.get(Idea, idea_id)
    prof = latest_profile(s, author_id, locked_only=True) or latest_profile(s, author_id)
    if idea is None or prof is None:
        raise RuleError("Pick an idea and build a voice profile first.")
    note, writer = "", "offline stand in"
    if ctx.model_on() and ctx.settings.draft_writer == "model":
        author = s.get(Author, author_id)
        res = model_tasks.write_variants(ctx.llm(s), prof.stats, author.name.replace(" (fictional)", ""), prof.guide, {"title": idea.title, "evidence": idea.evidence}, kind, 2,
                                         lambda t: evaluate(s, ctx.effective(s), author_id, t, list(idea.note_ids)), ctx.settings.min_voice_match)
        vs, note, writer = res.value, res.note, res.writer  # type: ignore[assignment]
    else:
        vs = writers.write(prof.stats, {"title": idea.title, "evidence": idea.evidence}, kind)
    d = Draft(author_id=author_id, idea_id=idea.id, kind=kind, title=idea.title[:150], text=vs[0]["text"], source_note_ids=list(idea.note_ids), created_by=actor, created_at=ctx.now(s), updated_at=ctx.now(s))
    s.add(d)
    s.flush()
    for v in vs:
        s.add(Variant(draft_id=d.id, label=v["label"], text=v["text"], note=(v.get("note") or writers.OFFLINE_LABEL)[:290]))
    idea.status = "approved"
    record_audit(s, actor, "draft.created", f"draft:{d.id}", {"idea": idea.id, "kind": kind, "writer": writer, "status": d.status, **({"note": note} if note else {})})
    return d


def load_ideas(s: Session, notes: list[Note], ctx=None) -> int:
    for i in s.scalars(select(Idea).where(Idea.status == "inbox")):  # ideas already used for a draft, or dropped on purpose, stay
        s.delete(i)
    s.flush()
    kept_titles = {i.title for i in s.scalars(select(Idea))}
    src = {n.id: n.text for n in notes}
    rows = [{"id": n.id, "kind": n.kind, "text": n.text} for n in notes]
    out = ideas.find_ideas(rows)
    if ctx is not None and ctx.model_on() and ctx.settings.idea_finder == "model" and rows:
        res = model_tasks.propose_ideas(ctx.llm(s), rows, out)
        out = sorted(out + list(res.value), key=lambda i: -i.score)  # type: ignore[operator]
        record_audit(s, "system", "ideas.model_proposed", None, {"writer": res.writer, "added": len(res.value), **({"note": res.note} if res.note else {})})  # type: ignore[arg-type]
    kept = 0
    for i in out:
        ev = [e for e in i.evidence if ideas.verify_quote(src[e["note_id"]], e["quote"])]  # a quote that is not in its source is dropped
        if not ev or i.title in kept_titles:
            continue
        s.add(Idea(title=i.title, evidence=ev, note_ids=i.note_ids, score=i.score, parts=i.parts))
        kept += 1
    s.flush()
    return kept
