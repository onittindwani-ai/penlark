"""Round 6: what the fourth audit found. A link like text that crashed the link guard, bare addresses that slipped past it, copies of a deleted note's words, and the cheap lows.
One test per fix; each failed before its fix."""

from __future__ import annotations

import json
import sqlite3

import httpx
import pytest
from hardening_helpers import DATA, approve_the_waiting_draft, live_app, real_client
from hardening_helpers import login as real_login
from sqlalchemy import select

from conftest import login as demo_login
from penlark import attribution, service
from penlark.config import Settings
from penlark.models import Draft, Idea, Link, Note, Schedule, Variant

ALLOW = Settings(redirect_allow_hosts="example.org", public_base_url="http://localhost:3000", _env_file=None)

# ---- 1. text that looks like a link but is not one must never crash the guard ----

CRASHERS = [
    "Reply at https://[YOUR LINK] today",
    "Read https://[abc now",
    "Read https://[x",
    "详见 https://evil.com：现在",
    "see https://evil.com／x ok",
    "https://[::1",
    "link: http://[fe80::1%zone]/x",
]


@pytest.mark.parametrize("text", CRASHERS)
def test_a_link_like_string_never_crashes_the_guard_and_is_flagged(text):
    found = service.foreign_links(text, ALLOW)
    assert found, text


def test_an_allowed_link_followed_by_cjk_punctuation_is_still_the_owners():
    for text in ("详见 https://example.org：现在", "详见https://example.org，现在", "看 https://example.org／x 吧", "https://example.org。", "（https://example.org）"):
        assert service.foreign_links(text, ALLOW) == [], text


def test_a_fullwidth_or_ideographic_dot_does_not_hide_a_foreign_address():
    for text in ("go to ｅｖｉｌ．ｃｏｍ now", "go to evil。com now", "go to evil｡com now"):
        assert service.foreign_links(text, ALLOW), text


def test_host_allowed_is_false_not_an_error_for_a_malformed_address():
    for url in ("https://[x", "https://[YOUR LINK]", "https://example.org：现在", "https://example.org／x", "https://[::1"):
        assert attribution.host_allowed(url, ["example.org"]) is False, url


def test_the_link_maker_answers_422_for_a_malformed_address_and_never_500(client):
    h = demo_login(client)
    for target in ("https://[x", "https://[YOUR LINK]", "https://[::1"):
        r = client.post("/api/links", headers=h, json={"target": target, "campaign": "c1"})
        assert r.status_code == 422, (target, r.status_code, r.text)


def test_a_stored_malformed_target_is_gone_not_a_crash(client):
    h = demo_login(client)
    ctx = client.app.state.ctx
    with ctx.factory() as s:
        s.add(Link(code="bad9999", target="https://[x", post_ref="", source="s", medium="m", campaign="c"))
        s.commit()
    assert client.get("/api/public/r/bad9999", follow_redirects=False).status_code == 410


@pytest.mark.parametrize("text", ["Pay here https://[YOUR LINK] now, it is good.", "详见 https://[abc：现在", "Read https://[x"])
def test_a_saved_draft_with_such_text_still_opens_matches_and_cannot_be_approved(client, text):
    h, a = demo_login(client), demo_login(client, "approver@example.test")
    assert client.put("/api/drafts/2", headers=h, json={"text": text}).status_code == 200
    r = client.get("/api/drafts/2", headers=h)
    assert r.status_code == 200 and r.json()["evaluation"]["links"] and r.json()["evaluation"]["ready"] is False
    m = client.post("/api/match", headers=h, json={"author_id": 1, "text": text})
    assert m.status_code == 200 and m.json()["ready"] is False
    ask = client.post("/api/drafts/2/request-approval", headers=h)
    assert ask.status_code == 409, ask.text  # refused with a reason, not a crash
    # a draft that already waits for approval and whose words are then changed in the database: deciding must also be a clean answer
    ctx = client.app.state.ctx
    from sendora_core.models import Approval

    with ctx.factory() as s:
        d = s.get(Draft, 1)
        d.text = text
        pend = s.scalars(select(Approval).where(Approval.status == "pending")).first()
        pend.payload = {**pend.payload, "text_sha256": service.text_digest(text)}
        aid = pend.id
        s.commit()
    r = client.post(f"/api/approvals/{aid}/decide", headers=a, json={"approve": True})
    assert r.status_code == 409, r.text


# ---- 2. a bare address is an address however it is written ----

FLAGGED = [
    "EVIL.COM", "evil.COM", "Evil.Com/x", "Evil.Com", "evil.zip", "evil.zip/x", "EVIL.ZIP", "evil.tk", "evil.cam", "evil.rest", "evil.mov", "evil.icu",
    "пример.рф", "пример.рф/путь", "bücher.de", "bücher.de/x", "xn--bcher-kva.de", "xn--e1afmkfd.xn--p1ai", "evil.com现在", "evil.com/x", "sub.evil.com/a/b",
    "evil.foo/path", "Evil.Foo/Path", "evil.zip:8080", "bit.ly/x", "BIT.LY/x", "T.CO/abc",
]
NOT_FLAGGED = [
    "We shipped it.It works.", "Done.In time.", "It is fine.So we go.", "Written by Dr.Smith in v1.2.3.", "We use Next.js, e.g. for the site, and file.txt stays.", "Costs 3.5 percent.",
    "See README.md and main.py today.", "Use node.js/express rarely", "example.org", "EXAMPLE.ORG/pricing", "Example.Org", "Works.Then it stops.",
]


@pytest.mark.parametrize("text", FLAGGED)
def test_bare_addresses_in_any_case_script_or_ending_are_flagged(text):
    assert service.foreign_links(f"Take a look at {text} before you decide.", ALLOW), text


@pytest.mark.parametrize("text", NOT_FLAGGED)
def test_plain_words_with_a_dot_and_the_owners_own_host_are_not_flagged(text):
    assert service.foreign_links(text, ALLOW) == [], text


# ---- 3. a deleted note leaves no copy of its words ----

def _text_values(db_path: str):
    """Every text or JSON value of every column of every table of the database file."""
    con = sqlite3.connect(db_path)
    try:
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            cols = [c[1] for c in con.execute(f'PRAGMA table_info("{table}")')]
            for row in con.execute(f'SELECT * FROM "{table}"'):
                for col, val in zip(cols, row):
                    if isinstance(val, str):
                        yield table, col, row, val
    finally:
        con.close()


def _copies(db_path: str, needles: list[str], skip_draft_ids: set[int]):
    out = []
    for table, col, row, val in _text_values(db_path):
        if table == "vp_note" and col == "text":
            continue
        if table == "vp_draft" and col == "text" and row[0] in skip_draft_ids:
            continue
        if table == "vp_variant" and col == "text" and row[1] in skip_draft_ids:
            continue
        for n in needles:
            if n and n in val:
                out.append((table, col, n[:40]))
    return out


def _db_path(client) -> str:
    return str(client.app.state.ctx.settings.database_url).removeprefix("sqlite:///")


def _forms(quote: str) -> list[str]:
    from penlark import writers

    core = writers._clean_quote(quote).rstrip(".?! ")
    return [quote, core, writers.contract(core, True), writers.contract(core, False), quote[:70].rstrip(" .,;:!?")]


def test_deleting_a_note_leaves_its_words_in_no_title_variant_or_approval(client):
    h = demo_login(client)
    ctx = client.app.state.ctx
    with ctx.factory() as s:
        idea = s.scalars(select(Idea).where(Idea.status == "inbox")).first()
        iid, nid, quote = idea.id, idea.evidence[0]["note_id"], idea.evidence[0]["quote"]
    d = client.post(f"/api/ideas/{iid}/draft", headers=h, json={"author_id": 1, "kind": "email"})
    assert d.status_code == 200, d.text
    did = d.json()["id"]
    ask = client.post(f"/api/drafts/{did}/request-approval", headers=h)  # may be refused (brackets): then there is no approval, which is fine
    needles = [f for f in _forms(quote) if len(f) >= 20]
    assert _copies(_db_path(client), needles, set()), "set up: the quote must be stored in a title or a variant before the delete"
    r = client.delete(f"/api/notes/{nid}", headers=h)
    assert r.status_code == 200, r.text
    left = _copies(_db_path(client), needles, set(r.json()["drafts_still_quoting_it"]))
    assert left == [], left
    assert "titles_cleared" in r.json() and "variants_removed" in r.json()
    assert ask.status_code in {200, 409}


def test_a_kept_idea_gets_a_new_title_from_the_evidence_that_is_left(client):
    h = demo_login(client)
    ctx = client.app.state.ctx
    q1 = "Our invoices keep getting paid forty days late and nobody tells us why."
    q2 = "Why does every client pay the second reminder but never the first one?"
    with ctx.factory() as s:
        n1, n2 = Note(kind="email", text=q1), Note(kind="email", text=q2)
        s.add_all([n1, n2])
        s.flush()
        idea = Idea(title=q1[:70].rstrip(" .,;:!?"), evidence=[{"note_id": n1.id, "quote": q1, "start": 0}, {"note_id": n2.id, "quote": q2, "start": 0}], note_ids=[n1.id, n2.id], status="inbox")
        s.add(idea)
        s.commit()
        iid, n1id = idea.id, n1.id
    assert client.delete(f"/api/notes/{n1id}", headers=h).status_code == 200
    with ctx.factory() as s:
        i = s.get(Idea, iid)
        assert i is not None and "forty days" not in i.title and i.title == q2[:70].rstrip(" .,;:!?")
    assert _copies(_db_path(client), [q1, q1[:40]], set()) == []


def test_a_variant_that_is_the_drafts_own_text_stays_and_the_draft_is_listed(client):
    h = demo_login(client)
    ctx = client.app.state.ctx
    q = "Why does every client pay the second reminder but never the first one?"
    with ctx.factory() as s:
        n = Note(kind="email", text=q)
        s.add(n)
        s.flush()
        idea = Idea(title=q[:70], evidence=[{"note_id": n.id, "quote": q, "start": 0}], note_ids=[n.id], status="inbox")
        s.add(idea)
        s.flush()
        d = Draft(author_id=1, idea_id=idea.id, title=q[:70], text=f"Someone asked: {q} Here is my answer.", source_note_ids=[n.id], status="draft")
        s.add(d)
        s.flush()
        s.add_all([Variant(draft_id=d.id, label="A", text=d.text), Variant(draft_id=d.id, label="B", text=f"Another way: {q}")])
        s.commit()
        nid, did = n.id, d.id
    r = client.delete(f"/api/notes/{nid}", headers=h).json()
    assert r["drafts_still_quoting_it"] == [did] and r["variants_removed"] == 1 and r["titles_cleared"] == 1
    with ctx.factory() as s:
        assert [v.label for v in s.scalars(select(Variant).where(Variant.draft_id == did))] == ["A"]
        assert q[:30] not in s.get(Draft, did).title


def test_deleting_a_sample_also_clears_variants_that_quote_its_sentences(client):
    h = demo_login(client)
    ctx = client.app.state.ctx
    from penlark.models import Sample, VoiceProfile

    with ctx.factory() as s:
        samples = list(s.scalars(select(Sample).where(Sample.author_id == 1)))
        sentences = {x for p in s.scalars(select(VoiceProfile).where(VoiceProfile.author_id == 1)) for v in p.examples.values() for x in v}
        pick = next(x for x in samples if any(t in x.text and len(t) >= 20 and not any(t in o.text for o in samples if o.id != x.id) for t in sentences))
        mine = next(t for t in sentences if t in pick.text and len(t) >= 20 and not any(t in o.text for o in samples if o.id != pick.id))
        d = Draft(author_id=1, title="Variants of a draft", text="Plain own words here.", status="draft")
        s.add(d)
        s.flush()
        s.add(Variant(draft_id=d.id, label="B", text=f"Quoted: {mine}"))
        s.commit()
        sid = pick.id
    r = client.delete(f"/api/samples/{sid}", headers=h)
    assert r.status_code == 200 and r.json()["variants_removed"] == 1, r.text
    assert _copies(_db_path(client), [mine], set()) == []


# ---- 4. the cheap lows ----

def test_a_read_only_post_does_not_take_the_write_lock(tmp_path):
    c = real_client(tmp_path)
    h = real_login(c)  # the owner: a post that only reads must still not take the write lock
    ctx = c.app.state.ctx
    calls = []
    real = ctx.write_factory

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)

    if real is None:
        pytest.skip("this database has no separate write lock")
    ctx.write_factory = spy
    c.post("/api/match", headers=h, json={"author_id": 1, "text": "Hello there, this is plain."})
    c.post("/api/profile/compare", headers=h, json={"author_id": 1, "text": "Hello there."})
    assert calls == []


def test_a_nul_in_a_decision_note_or_a_comparison_text_is_taken_out(client):
    h, a = demo_login(client), demo_login(client, "approver@example.test")
    r = client.post("/api/profile/compare", headers=h, json={"author_id": 1, "text": "Plain words\x00 here, nothing more."})
    assert r.status_code == 200
    ctx = client.app.state.ctx
    pend = next(x for x in client.get("/api/approvals", headers=h).json() if x["status"] == "pending")
    r = client.post(f"/api/approvals/{pend['id']}/decide", headers=a, json={"approve": False, "note": "no\x00pe"})
    assert r.status_code == 200
    from sendora_core.models import Approval

    with ctx.factory() as s:
        assert "\x00" not in (s.get(Approval, pend["id"]).decision_note or "")


def test_the_web_proxy_refuses_the_public_tree_and_does_not_follow_redirects():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "apps" / "web"
    guard = (root / "src/lib/proxyGuard.ts").read_text()
    route = (root / "app/api/[...path]/route.ts").read_text()
    assert '"public"' in guard.split("BLOCKED_FIRST")[1].split("\n")[0]
    assert 'redirect: "manual"' in route


def _send_body(rec):
    return json.loads(rec.posts[-1])


def test_a_send_goes_out_at_the_send_hour_in_the_owners_timezone_not_at_midnight_utc(tmp_path):
    c, rec, ctx = live_app(tmp_path, timezone="America/New_York", send_hour=9)
    h, did = approve_the_waiting_draft(c)
    r = c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False, "run_on": "2026-12-10"})
    assert r.status_code == 200, r.text
    assert _send_body(rec)["date"] == "2026-12-10T14:00:00.000Z"  # 9:00 in New York in December


def test_a_date_that_has_already_passed_is_refused_and_nothing_is_sent(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    r = c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False, "run_on": "2026-11-01"})
    assert r.status_code == 400 and "past" in r.json()["error"]["message"].lower() and rec.posts == []
    with ctx.factory() as s:
        assert s.get(Draft, did).status == "approved"


def test_buffer_cannot_take_a_date_so_a_date_is_refused_instead_of_ignored(tmp_path):
    from penlark.adapters.schedulers import Buffer

    c, rec, ctx = live_app(tmp_path, buffer_token="bf-test-only-token", scheduler_adapter="buffer")
    posted = []
    ctx.scheduler = Buffer(ctx.settings, httpx.Client(base_url="https://api.buffer.test", transport=httpx.MockTransport(lambda req: posted.append(req) or httpx.Response(200, json={}))))
    h, did = approve_the_waiting_draft(c)
    r = c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False, "run_on": "2026-12-10"})
    assert r.status_code == 400 and "Buffer" in r.json()["error"]["message"] and posted == []


def test_a_second_send_while_the_first_is_out_does_not_delete_the_first_sending_row(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    with ctx.factory() as s:
        d = s.get(Draft, did)
        d.status = "sending"
        s.add(Schedule(draft_id=did, platform="linkedin", run_on="2026-12-02", status="sending", adapter="postiz"))
        s.commit()
    r = c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False})
    assert r.status_code == 409 and "being sent" in r.json()["error"]["message"]
    with ctx.factory() as s:
        assert s.scalar(select(Schedule.id).where(Schedule.draft_id == did, Schedule.status == "sending")) is not None
        assert s.get(Draft, did).status == "sending" and rec.posts == []


def test_send_outcome_keeps_the_platform_of_the_send(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    with ctx.factory() as s:
        s.get(Draft, did).status = "send_unknown"
        s.add(Schedule(draft_id=did, platform="x", run_on="2026-12-02", status="planned", adapter="plan"))
        s.commit()
    r = c.post(f"/api/drafts/{did}/send-outcome", headers=h, json={"posted": True, "external_id": "p1"})
    assert r.status_code == 200, r.text
    with ctx.factory() as s:
        rows = list(s.scalars(select(Schedule).where(Schedule.draft_id == did, Schedule.status == "sent")))
        assert [x.platform for x in rows] == ["x"]


def test_the_docs_run_the_admin_command_from_the_virtual_environment():
    from pathlib import Path

    docs = Path(__file__).resolve().parents[3] / "docs"
    for name in ("05-RUN-LOCALLY.md", "15-TROUBLESHOOTING.md", "10-USING-IT-FOR-A-CLIENT.md", "09-GO-LIVE-CHECKLIST.md"):
        for line in (docs / name).read_text().splitlines():
            if "python -m penlark.admin" in line:
                assert ".venv/bin/python -m penlark.admin" in line, f"{name}: {line[:100]}"
