"""The orchestration layer: everything the API does with the database goes through here, so the rules live in one place."""

from __future__ import annotations

import hashlib
import json
import re
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


PROFILE_MAX_SAMPLES = 500  # the newest samples that are measured for one voice
PROFILE_MAX_CHARS = 1_500_000  # and no more text than this in all, so a huge export cannot hold the API for minutes


def samples_for_profile(s: Session, author_id: int) -> list[Sample]:
    """The newest samples of a voice that fit the bounds, oldest first."""
    kept: list[Sample] = []
    total = 0
    for row in s.scalars(select(Sample).where(Sample.author_id == author_id).order_by(Sample.id.desc()).limit(PROFILE_MAX_SAMPLES)):
        if kept and total + len(row.text) > PROFILE_MAX_CHARS:
            break
        kept.append(row)
        total += len(row.text)
    kept.reverse()
    return kept


def sample_digest(text: str) -> str:
    """The same words with other spacing or capitals are the same sample."""
    return hashlib.sha256(" ".join(text.split()).lower().encode("utf-8")).hexdigest()


def sample_digests(s: Session, author_id: int) -> set[str]:
    """One set per request, so adding many samples at once compares each against a set, not against every stored text again."""
    return {sample_digest(t) for t in s.scalars(select(Sample.text).where(Sample.author_id == author_id))}


def build_profile(s: Session, author_id: int, actor: str, ctx=None) -> VoiceProfile:
    author = s.get(Author, author_id)
    samples = samples_for_profile(s, author_id)
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
    links = foreign_links(text, settings)
    return {"match": m, "rules": checks, "placeholders": brackets, "links": links, "profile_version": prof.version if prof else None, "profile_locked": bool(prof and prof.locked),
            "ready": bool(m["score"] >= settings.min_voice_match and checks["ok"] and not brackets and not links)}


def readiness_problem(ev: dict, min_match: float) -> str | None:
    """Why a draft may not go to a second person, in plain words, or None when it may. One place, so asking and approving use the same bar."""
    if ev["placeholders"]:
        return "Fill the [BRACKETS] with your own real words first: " + ", ".join(ev["placeholders"][:4]) + "."
    if ev.get("links"):
        return "A link or address in the text is not yours: " + ", ".join(ev["links"][:3]) + ". Take it out, or add its host to REDIRECT_ALLOW_HOSTS if it is yours."
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


# A placeholder such as [YOUR CLIENT NAME]. Both repeats have an upper limit: with open ended repeats a text of "[" and 30,000 capital letters took seconds per check.
_BRACKETS = re.compile(r"\[[A-Z][A-Z0-9 ,'\-]{2,200}[A-Z0-9\]]{0,8}\]")


def _brackets(text: str) -> list[str]:
    return _BRACKETS.findall(text)


# A link, a web address or an email address typed in a draft. The repeats have upper limits so a hostile text cannot make this slow.
_LINKS = re.compile(r"https?://[^\s<>\"')]{1,300}|\bwww\.[^\s<>\"')]{1,300}|[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,5}", re.I)


def foreign_links(text: str, settings) -> list[str]:
    """Links and addresses in a draft that do not belong to the owner: not on REDIRECT_ALLOW_HOSTS and not the host of PUBLIC_BASE_URL. Text from a comment or an email
    can carry a link a person never meant to publish, so each one must be a deliberate choice."""
    from urllib.parse import urlparse

    from penlark import attribution

    allow = [*settings.allow_hosts(), urlparse(settings.public_base_url).hostname or ""]
    out: list[str] = []
    for found in _LINKS.findall(text):
        raw = found.rstrip(".,;:!?")
        host = raw.rsplit("@", 1)[1] if "@" in raw and "://" not in raw and not raw.lower().startswith("www.") else (urlparse(raw if "://" in raw else "https://" + raw).hostname or "")
        if not attribution.host_matches(host, allow) and raw not in out:
            out.append(raw)
    return out


def text_digest(text: str) -> str:
    """The fingerprint of the exact words. An approval is for these words only: change one character and the fingerprint changes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def binding_problem(s: Session, d: Draft) -> str | None:
    """Why this draft's text is not the text a second person approved, or None when it is. Used before anything leaves the app."""
    from sendora_core.models import Approval

    a = s.get(Approval, d.approval_id) if d.approval_id else None
    if a is None or a.action != "draft.approve" or a.status != "approved":
        return "There is no approval on record for this draft. Ask a second person to approve it."
    want = (a.payload or {}).get("text_sha256")
    if not want:
        return "This approval was made before approvals were tied to the exact text. Ask a second person to approve the draft again."
    if want != text_digest(d.text):
        return "The text is not the text that was approved. Ask a second person to approve this version."
    return None


def _aware(moment):
    """SQLite gives back a time with no zone. Everything here is UTC."""
    from datetime import UTC

    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


SEND_HOLD = timedelta(minutes=30)  # a draft marked "sending" this long ago was left behind by a send that never finished


def lock_draft(s: Session, draft_id: int, ctx=None) -> Draft | None:
    """Read the draft and hold its row (on Postgres) until this request ends, so an edit and a decision cannot run through each other.
    With `ctx`, a draft left in "sending" for over half an hour (the app stopped during the send) goes back to approved, with a record: the person is told to check the scheduling tool first."""
    d = s.execute(select(Draft).where(Draft.id == draft_id).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if d is not None and ctx is not None and d.status == "sending" and ctx.now(s) - _aware(d.updated_at) > SEND_HOLD:
        d.status = "approved"
        record_audit(s, "system", "draft.send_released", f"draft:{d.id}", {"after_minutes": int(SEND_HOLD.total_seconds() // 60)})
    return d


def ensure_builtin_rules(s: Session) -> int:
    """Make sure the built in banned phrases and patterns exist as rows (a person can turn each off, never delete it). Safe to run on every start."""
    have = {(r.kind, r.value) for r in s.scalars(select(HouseRule).where(HouseRule.builtin.is_(True)))}
    added = 0
    for ph in house_rules.DEFAULT_BANNED:
        if ("phrase", ph) not in have:
            s.add(HouseRule(kind="phrase", value=ph, note="Built in: a generic phrase that sounds machine written.", builtin=True))
            added += 1
    for pat, why in house_rules.DEFAULT_PATTERNS:
        if ("pattern", pat) not in have:
            s.add(HouseRule(kind="pattern", value=pat, note=why, builtin=True))
            added += 1
    s.flush()
    return added


def unique_author_slug(s: Session, name: str) -> str:
    from penlark import attribution

    base = attribution.slug(name) or "voice"
    taken = set(s.scalars(select(Author.slug)))
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base[:36]}-{n}", n + 1
    return slug


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


def recent_notes(s: Session) -> list[Note]:
    """The newest notes the idea finder will look at, oldest first. The limit is applied in the query, so a long history is never loaded."""
    rows = list(s.scalars(select(Note).order_by(Note.id.desc()).limit(ideas.MAX_NOTES)))
    rows.reverse()
    return rows


def load_ideas(s: Session, notes: list[Note], ctx=None) -> int:
    for i in s.scalars(select(Idea).where(Idea.status == "inbox")):  # ideas already used for a draft, or dropped on purpose, stay
        s.delete(i)
    s.flush()
    kept_titles = {i.title for i in s.scalars(select(Idea))}
    src = {n.id: n.text for n in notes}
    rows = ideas.limit_notes([{"id": n.id, "kind": n.kind, "text": n.text} for n in notes])
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
