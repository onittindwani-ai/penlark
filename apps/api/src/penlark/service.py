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
from penlark.models import Author, Click, Conversion, Draft, Experiment, HouseRule, Idea, Link, Note, Performance, Sample, Schedule, Variant, VoiceProfile
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
    """One set per request, so adding many samples at once compares each against a set, not against every stored text again. The library is read in batches and only the
    short digests are kept, so a large library is never held in memory whole. Callers run it on a worker thread: hashing a big library takes a moment."""
    return {sample_digest(t) for t in s.scalars(select(Sample.text).where(Sample.author_id == author_id).execution_options(yield_per=200))}


def build_profile(s: Session, author_id: int, actor: str, ctx=None) -> VoiceProfile:
    author = s.get(Author, author_id)
    if author is None:
        raise RuleError("No such voice.")
    samples = samples_for_profile(s, author_id)
    if not samples:
        raise RuleError("Add at least one writing sample first.")
    texts = [x.text for x in samples]
    stats = fingerprint.build_profile(texts)
    prev = latest_profile(s, author_id)
    name = author.name.replace(" (sample)", "")
    text, source, note = guide.offline_guide(stats, name), "offline stand in", ""
    if ctx is not None and ctx.model_on() and ctx.settings.guide_writer == "model" and not (prev and prev.locked):
        eff = ctx.effective(s)
        s.commit()  # the write lock is let go before the model is asked: it can take minutes, and nothing else could write meanwhile
        res = model_tasks.write_guide(ctx.llm_detached(eff), stats, name, texts)
        text, source, note = res.value, res.writer, res.note  # type: ignore[assignment]
        prev = latest_profile(s, author_id)  # another request may have added a version, or locked one, while the model answered
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
# A web address with no http in front: "evil.com/free" or "bit.ly/x". A label may hold any letter or digit (a domain such as "bücher.de" or "пример.рф" is an address). Plain words with a dot in them
# ("Next.js", "e.g.", "file.txt") are not addresses, so only a known web ending counts, a link shortener, or any ending followed by a path ("evil.foo/x"). The ending is read in lower case.
_LABEL = r"[^\W_](?:[\w-]{0,61}[^\W_])?"
_BARE = re.compile(rf"(?<![\w@./:-])((?:{_LABEL}\.){{1,4}}(xn--[a-z0-9-]{{2,59}}|[a-z]{{2,24}}|[^\W\d_]{{2,24}}))(?::\d{{1,5}})?(?:/[^\s<>\"')]{{0,300}})?(?![a-z0-9-])", re.I)
_CC = ("ad ae af ag al ao ar at au az ba bb bd be bf bg bh bi bj bm bn bo br bs bt bw bz ca cd cf cg ch ci ck cl cm cn co cr cu cv cx cy cz de dj dk dm dz ec ee eg er es et eu fi fj fo fr ga ge gf gg gh gi gl gm gn gp gq gr gt gu gw gy hk hn hr ht hu id ie il im in io iq ir it je jm jo jp ke kg kh ki km kn kp kr kw ky kz lb lc li lk lr ls lt lu lv ly mc me mg mk ml mm mn mq mr ms mt mu mv mw mx mz na nc ne nf ng ni nl no np nr nu nz om pe pf pg ph pk pl pm pn pr ps pt pw qa ro rw sa sb sc sd se sg sh si sk sl sm sn sr sv sx sy sz tc td tg th tj tk tl tm tn to tr tt tv tw tz ua ug uk us uy uz vc ve vg vi vn vu wf ws ye yt za zm zw")
_GTLD = ("com net org info biz mobi asia xyz app dev ai page top vip click link live news online site store shop tech cloud club ink zip mov cam rest icu buzz monster world today space website email digital agency solutions center network systems services "
         "support group company lol host wiki casino poker bingo porn sex adult xxx stream download review party science loan bid trade racing gmbh ltd inc llc casa kim lat ooo ovh wang xin")
_IDN_TLDS = frozenset("рф рус онлайн сайт москва дети орг ком бел укр срб католик 中国 中國 中文网 网站 网络 公司 香港 台湾 台灣 新加坡 日本 한국 닷컴 ไทย भारत ভারত இந்தியா السعودية مصر امارات اونلاين شبكة موقع קום".split())
_TLDS = frozenset((_CC + " " + _GTLD).split()) | frozenset("ly gl".split())
_FILE_ENDINGS = frozenset("js jsx ts tsx json md py rs txt html htm css yml yaml csv pdf png jpg jpeg gif svg docx xlsx pptx toml ini cfg log rb php java kt swift go c h cpp lock env conf".split())
# Words that start a sentence and are also a web ending ("Done.It works"): skipped only when the first letter is a capital, the rest is lower case, and there is no path or port.
_SENTENCE_WORDS = frozenset("it in is at as my so no to me us be by go id am an do he we of on or up if ok hi".split())
_SHORTENERS = frozenset("bit.ly t.co tinyurl.com goo.gl ow.ly buff.ly lnkd.in is.gd rb.gy cutt.ly t.ly shorturl.at rebrand.ly tiny.cc s.id trib.al dlvr.it youtu.be amzn.to fb.me wp.me".split())
# Punctuation of Chinese, Japanese and Korean writing that ends an address (a full width colon, slash, comma or full stop right after it); a browser cannot go to a host that holds one.
_LINK_ENDERS = str.maketrans({c: " " for c in "，。；：！？、）（」「』『】【》《〉〈”“’‘／＼"})
_IDEOGRAPHIC_DOT = re.compile(r"(?<=[A-Za-z0-9-])[。｡](?=[A-Za-z0-9])")  # `evil。com`: a browser reads this full stop as a dot in a host name


def scan_text(text: str) -> str:
    """The text as an address scan should read it: the ideographic full stop inside an address is a dot, the punctuation that ends an address ends it, and every full width letter, digit,
    dot and at sign is the plain one a browser would make of it."""
    import unicodedata

    return unicodedata.normalize("NFKC", _IDEOGRAPHIC_DOT.sub(".", text).translate(_LINK_ENDERS))


def _host_of(raw: str) -> str | None:
    """The host a browser would go to for this address, or None when the address is written so that a parser and a browser could read it differently:
    a backslash (`https://evil.com\\@example.org/x` is read as evil.com by a browser and as example.org by a parser), a user name or a password in front of the host,
    or text that cannot be an address at all (`https://[YOUR LINK]`, which makes the parser stop with an error)."""
    from penlark import attribution

    if "\\" in raw:
        return None
    u = attribution.parse_address(raw if "://" in raw else "https://" + raw)
    if u is None:
        return None
    try:
        if u.username is not None or u.password is not None or "@" in u.netloc:
            return None
        return u.hostname or ""
    except ValueError:
        return None


def _known_ending(tld: str, domain: str) -> bool:
    return tld in _TLDS or domain in _SHORTENERS or tld.startswith("xn--") or any(tld.startswith(i) for i in _IDN_TLDS if not i.isascii())


def foreign_links(text: str, settings) -> list[str]:
    """Links and addresses in a draft that do not belong to the owner: not on REDIRECT_ALLOW_HOSTS and not the host of PUBLIC_BASE_URL. Text from a comment or an email
    can carry a link a person never meant to publish, so each one must be a deliberate choice. An address written two ways at once (a backslash, a name and password in front
    of the host) is always foreign, and so is a bare address such as `evil.com/free` (in any case or script) or a shortened link such as `bit.ly/x`. Text that only looks like a link
    (`https://[YOUR LINK]`) is flagged too, never a crash."""
    from urllib.parse import urlparse

    from penlark import attribution

    allow = [*settings.allow_hosts(), urlparse(settings.public_base_url).hostname or ""]
    out: list[str] = []

    def flag(raw: str) -> None:
        if raw not in out:
            out.append(raw)

    text = scan_text(text)
    for found in _LINKS.findall(text):
        raw = found.rstrip(".,;:!?")
        if "@" in raw and "://" not in raw and not raw.lower().startswith("www."):
            host = raw.rsplit("@", 1)[1]
        else:
            host = _host_of(raw)
        if host is None or not attribution.host_matches(host, allow):
            flag(raw)
    rest = _LINKS.sub(" ", text)  # what is left once the addresses above are taken out: look for bare ones
    for m in _BARE.finditer(rest):
        domain, tld_raw = m.group(1).lower(), m.group(2)
        tld = tld_raw.lower()
        has_path = "/" in m.group(0)
        plain_end = m.group(0) == m.group(1)
        if plain_end and tld_raw[:1].isupper() and tld_raw[1:].islower() and tld in _SENTENCE_WORDS and domain.count(".") == 1:
            continue  # "Done.It works" is a missing space after a full stop, not an address
        if not (_known_ending(tld, domain) or (has_path and tld not in _FILE_ENDINGS)):
            continue
        if not attribution.host_matches(domain, allow):
            flag(m.group(0).rstrip(".,;:!?"))
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


def hold_unclear_send(s: Session, d: Draft, actor: str, adapter: str, platform: str, run_on: str, reason: str = "") -> None:
    """A send whose outcome nobody knows: the draft stays out of reach (no second send, no edit) until a person checks the scheduling tool and says whether the post was made.
    The calendar row that was written when the send started (status "sending") becomes the "unclear" row; with none, one is made."""
    d.status = "send_unknown"
    detail = (f"{adapter} gave no clear answer. Check it, then say whether the post was made." + (f" {reason}" if reason else ""))[:300]
    row = s.scalars(select(Schedule).where(Schedule.draft_id == d.id, Schedule.status == "sending").order_by(Schedule.id.desc())).first()
    if row is None:
        row = Schedule(draft_id=d.id, platform=platform, run_on=run_on, adapter=adapter)
        s.add(row)
    row.status, row.external_id, row.detail = "unclear", "", detail
    record_audit(s, actor, "draft.send_unclear", f"draft:{d.id}", {"adapter": adapter, **({"reason": reason[:200]} if reason else {})})


def _read_draft(s: Session, draft_id: int) -> Draft | None:
    return s.execute(select(Draft).where(Draft.id == draft_id).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()


def lock_draft(s: Session, draft_id: int, ctx=None) -> Draft | None:
    """Read the draft and hold its row (on Postgres) until this request ends, so an edit and a decision cannot run through each other.
    With `ctx`, a draft left in "sending" for over half an hour (the app stopped during the send) is held like any other send with no clear answer: nobody knows whether the post was made,
    so it becomes "send_unknown" and a person checks the scheduling tool and says which it was. It is never put back to approved on its own."""
    d = _read_draft(s, draft_id)
    if d is not None and ctx is not None and d.status == "sending" and ctx.now(s) - _aware(d.updated_at) > SEND_HOLD:
        row = s.scalars(select(Schedule).where(Schedule.draft_id == d.id, Schedule.status == "sending").order_by(Schedule.id.desc())).first()
        hold_unclear_send(s, d, "system", row.adapter if row else ctx.scheduler.name, row.platform if row else "linkedin", row.run_on if row else ctx.today(s).isoformat(), f"The app stopped during the send, more than {int(SEND_HOLD.total_seconds() // 60)} minutes ago.")
        s.commit()  # kept even when this request then refuses to go on, so the draft does not look "being sent" for ever
        d = _read_draft(s, draft_id)
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
        eff, note_ids, idea_in = ctx.effective(s), list(idea.note_ids), {"title": idea.title, "evidence": idea.evidence}
        stats, guide_text, name = prof.stats, prof.guide, (author.name if author else "").replace(" (sample)", "")
        s.commit()  # the write lock is let go before the model is asked, and the re scoring of each variant reads in its own session

        def score(t: str) -> dict:
            with ctx.factory() as rs:
                return evaluate(rs, eff, author_id, t, note_ids)

        res = model_tasks.write_variants(ctx.llm_detached(eff), stats, name, guide_text, idea_in, kind, 2, score, ctx.settings.min_voice_match)
        vs, note, writer = res.value, res.note, res.writer  # type: ignore[assignment]
        idea = s.get(Idea, idea_id, populate_existing=True)  # read again: it may have been dropped while the model answered
        if idea is None:
            raise RuleError("That idea is gone. Find ideas again.")
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


def compute_ideas(rows: list[dict], ctx=None, eff=None) -> tuple[list, dict | None]:
    """The idea finder itself: plain code over the notes, and the model when one is on. It takes no session, so it holds no database lock (on hostile notes it can take seconds)."""
    out = ideas.find_ideas(rows)
    proposed = None
    if ctx is not None and ctx.model_on() and ctx.settings.idea_finder == "model" and rows:
        res = model_tasks.propose_ideas(ctx.llm_detached(eff or ctx.settings), rows, out)
        out = sorted(out + list(res.value), key=lambda i: -i.score)  # type: ignore[operator]
        proposed = {"writer": res.writer, "added": len(res.value), **({"note": res.note} if res.note else {})}  # type: ignore[arg-type]
    return out, proposed


def store_ideas(s: Session, found: list, src: dict[int, str], proposed: dict | None = None) -> int:
    for i in s.scalars(select(Idea).where(Idea.status == "inbox")):  # ideas already used for a draft, or dropped on purpose, stay
        s.delete(i)
    s.flush()
    kept_titles = {i.title for i in s.scalars(select(Idea))}
    if proposed is not None:
        record_audit(s, "system", "ideas.model_proposed", None, proposed)
    kept = 0
    for i in found:
        ev = [e for e in i.evidence if e["note_id"] in src and ideas.verify_quote(src[e["note_id"]], e["quote"])]  # a quote that is not in its source is dropped
        if not ev or i.title in kept_titles:
            continue
        s.add(Idea(title=i.title, evidence=ev, note_ids=i.note_ids, score=i.score, parts=i.parts))
        kept += 1
    s.flush()
    return kept


def load_ideas(s: Session, notes: list[Note], ctx=None) -> int:
    """Look through the notes again. The notes are read first, the write lock is let go, the finder runs with no session open, and only the result is written."""
    src = {n.id: n.text for n in notes}
    rows = ideas.limit_notes([{"id": n.id, "kind": n.kind, "text": n.text} for n in notes])
    eff = ctx.effective(s) if ctx is not None else None
    s.commit()  # nothing is pending yet: this only lets go of the write lock (a no-op for a read only session)
    found, proposed = compute_ideas(rows, ctx, eff)
    return store_ideas(s, found, src, proposed)
