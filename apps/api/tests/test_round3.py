"""Round 3: a sent post stays sent, a vendor 200 is not always a success, no network call holds the write lock, and the loop is never blocked by the database."""

from __future__ import annotations

import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from hardening_helpers import DATA, approve_the_waiting_draft, live_app
from sqlalchemy import select

from conftest import login as demo_login
from penlark.adapters.schedulers import UnclearAnswer, Buffer, Metricool, Postiz
from penlark.api.app import create_app
from penlark.config import Settings
from penlark.context import Ctx
from penlark.dbsetup import make_engine, make_factories
from penlark.models import Author, Draft, Note, Sample, Schedule, VoiceProfile
from sendora_core.adapters import AdapterError
from sendora_core.db import Base
from sendora_core.settings import Mode

WHEN = __import__("datetime").datetime(2026, 12, 2, 9, 0, tzinfo=__import__("datetime").timezone.utc)


def _send(c, h, did, **kw):
    return c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False, **kw})


def locked_app(tmp_path, handler, **kw):
    """A demo database in live mode on the SQLite write lock path (the one a real install uses), with a Postiz adapter served by `handler`. Returns (app, ctx)."""
    st = Settings(database_url=f"sqlite:///{tmp_path / 'locked.sqlite3'}", session_secret="test-secret-test-secret", seed_dir=DATA, mode=Mode.LIVE, postiz_api_key="pz-test-only-key",
                  lead_webhook_secret="hook-secret-for-tests", export_dir=str(tmp_path / "exports"), _env_file=None, **kw)
    eng = make_engine(st.database_url)
    Base.metadata.create_all(eng)
    factory, write_factory = make_factories(eng)
    adapter = Postiz(st, httpx.Client(base_url="http://postiz.test/public/v1", transport=httpx.MockTransport(handler)))
    ctx = Ctx(st, factory, scheduler=adapter, write_factory=write_factory)
    return create_app(st, ctx), ctx


# ---- 1. a sent post is never put back on the calendar for a second send ----

def test_a_sent_post_cannot_be_taken_off_the_calendar_and_sent_again(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    assert _send(c, h, did, as_draft=True).status_code == 200
    row = next(x for x in c.get("/api/schedule", headers=h).json() if x["draft_id"] == did and x["status"] == "sent")
    gone = c.delete(f"/api/schedule/{row['id']}", headers=h)
    assert gone.status_code == 409 and "already sent" in gone.json()["error"]["message"].lower()
    assert _send(c, h, did).status_code == 409 and len(rec.posts) == 1, "the second send must not reach the scheduling tool"
    assert any(x["id"] == row["id"] for x in c.get("/api/schedule", headers=h).json())


def test_only_a_planned_item_can_be_taken_off_the_calendar(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    assert c.post(f"/api/drafts/{did}/export", headers=h, json={}).status_code == 200
    row = next(x for x in c.get("/api/schedule", headers=h).json() if x["draft_id"] == did)
    assert row["status"] == "exported" and c.delete(f"/api/schedule/{row['id']}", headers=h).status_code == 409


# ---- 2. a vendor answer of 200 is a success only when it carries an id ----

BAD_POSTIZ = [{"message": "Invalid integration"}, [], [{"error": "no such channel"}], {"statusCode": 400}, "ok", [{"postId": ""}]]


@pytest.mark.parametrize("body", BAD_POSTIZ)
def test_postiz_200_without_a_post_id_is_unclear_not_scheduled(body):
    p = Postiz(Settings(mode=Mode.LIVE, demo_mode=False, session_secret="x" * 20, postiz_api_key="pz-test-only-key", _env_file=None), httpx.Client(base_url="http://postiz.test", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))))
    with pytest.raises(UnclearAnswer):
        p.send("Hello", "linkedin", WHEN, "ch-1", approved=True, confirm=True)


BAD_BUFFER = [{"errors": [{"message": "Unauthorized"}]}, {"data": None, "errors": [{"message": "boom"}]}, {"data": {"createPost": None}}, {"data": {"createPost": {"post": {}}}}, {"data": {"createPost": {"post": {"id": ""}}}}, {"data": {}}]


@pytest.mark.parametrize("body", BAD_BUFFER)
def test_buffer_200_without_a_post_id_is_unclear_not_saved(body):
    b = Buffer(Settings(mode=Mode.LIVE, demo_mode=False, session_secret="x" * 20, buffer_token="bf-test-only-token", _env_file=None), httpx.Client(base_url="http://buffer.test", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))))
    with pytest.raises(UnclearAnswer):
        b.send("Hello", "linkedin", WHEN, "chan-1", approved=True, confirm=True)


BAD_METRICOOL = [{"error": "bad blog"}, {"data": {}}, {"data": None}, {}, {"data": {"id": ""}}, []]


@pytest.mark.parametrize("body", BAD_METRICOOL)
def test_metricool_200_without_a_post_id_is_unclear_not_scheduled(body):
    m = Metricool(Settings(mode=Mode.LIVE, demo_mode=False, session_secret="x" * 20, metricool_token="mc-test-only-token", metricool_user_id="1", metricool_blog_id="2", _env_file=None),
                  httpx.Client(base_url="http://metricool.test", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))))
    with pytest.raises(UnclearAnswer):
        m.send("Hello", "linkedin", WHEN, approved=True, confirm=True)


def test_a_known_success_shape_still_gives_the_id():
    ok = lambda body: httpx.Client(base_url="http://x.test", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))  # noqa: E731
    st = dict(mode=Mode.LIVE, demo_mode=False, session_secret="x" * 20, _env_file=None)
    assert Postiz(Settings(postiz_api_key="k", **st), ok([{"postId": "pz-9", "integration": "c"}])).send("a", "linkedin", WHEN, "c", approved=True, confirm=True)["external_id"] == "pz-9"
    assert Buffer(Settings(buffer_token="k", **st), ok({"data": {"createPost": {"post": {"id": "bf-9"}}}})).send("a", "linkedin", WHEN, "c", approved=True, confirm=True)["external_id"] == "bf-9"
    assert Metricool(Settings(metricool_token="k", metricool_user_id="1", metricool_blog_id="2", **st), ok({"data": {"id": "mc-9"}})).send("a", "linkedin", WHEN, approved=True, confirm=True)["external_id"] == "mc-9"


def test_a_postiz_200_with_an_error_body_holds_the_draft_for_a_person(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    ctx.scheduler.client = httpx.Client(base_url="http://postiz.test/public/v1", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"message": "Invalid integration"})))
    r = _send(c, h, did)
    assert r.status_code == 502 and "may or may not" in r.json()["error"]["message"]
    with ctx.factory() as s:
        assert s.get(Draft, did).status == "send_unknown"
        assert not list(s.scalars(select(Schedule).where(Schedule.draft_id == did, Schedule.status == "sent")))
        assert [x.status for x in s.scalars(select(Schedule).where(Schedule.draft_id == did))] == ["unclear"]


def test_the_vendor_reply_is_kept_short_in_the_record_and_never_holds_a_long_id(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    ctx.scheduler.client = httpx.Client(base_url="http://postiz.test/public/v1", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[{"postId": "p" * 400}])))
    assert _send(c, h, did).status_code == 200
    with ctx.factory() as s:
        assert len(s.scalars(select(Schedule.external_id).where(Schedule.draft_id == did, Schedule.status == "sent")).one()) <= 120


# ---- 3. no network or model call holds the SQLite write lock ----

def test_a_slow_vendor_does_not_hold_the_write_lock(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def slow(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            entered.set()
            release.wait(30)
            return httpx.Response(200, json=[{"postId": "pz-1"}])
        return httpx.Response(200, json=[])

    app, ctx = locked_app(tmp_path, slow)
    c = TestClient(app, base_url="http://api.test")
    h, did = approve_the_waiting_draft(c)
    answer: dict = {}
    sender = threading.Thread(target=lambda: answer.update(r=_send(c, h, did, as_draft=True)))
    sender.start()
    try:
        assert entered.wait(10), "the send never reached the scheduling tool"
        other: dict = {}

        def write():
            t0 = time.perf_counter()
            other["r"] = c.post("/api/notes", headers=h, json={"kind": "note", "who": "A customer", "text": "A note written while another request waits for the scheduling tool."})
            other["took"] = time.perf_counter() - t0

        t = threading.Thread(target=write)
        t.start()
        t.join(6)
        assert not t.is_alive(), "a write had to wait for a send that was still out at the vendor"
        assert other["r"].status_code == 200 and other["took"] < 5
    finally:
        release.set()
        sender.join(20)
    assert answer["r"].status_code == 200
    with ctx.factory() as s:
        assert s.get(Draft, did).status == "scheduled" and s.scalars(select(Schedule).where(Schedule.draft_id == did, Schedule.status == "sent")).first() is not None


def test_the_claim_of_a_send_is_visible_while_the_vendor_is_still_answering(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def slow(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            entered.set()
            release.wait(30)
        return httpx.Response(200, json=[{"postId": "pz-1"}])

    app, ctx = locked_app(tmp_path, slow)
    c = TestClient(app, base_url="http://api.test")
    h, did = approve_the_waiting_draft(c)
    sender = threading.Thread(target=lambda: _send(c, h, did))
    sender.start()
    try:
        assert entered.wait(10)
        with ctx.factory() as s:
            assert s.get(Draft, did).status == "sending"
        assert _send(c, h, did).status_code == 409  # a second click while the first is out
    finally:
        release.set()
        sender.join(20)


def _model_app(tmp_path):
    """A demo database on the SQLite write lock path with every model job switched on. The model tasks themselves are replaced by the tests, so nothing is asked of any model."""
    from penlark.config import Settings as S
    from sendora_core.settings import LLMBackendKind

    st = S(database_url=f"sqlite:///{tmp_path / 'm.sqlite3'}", session_secret="test-secret-test-secret", seed_dir=DATA, export_dir=str(tmp_path / "exports"), lead_webhook_secret="hook-secret-for-tests",
           llm_backend=LLMBackendKind.FIXTURE, llm_fixtures_dir=str(__import__("pathlib").Path(DATA) / "llm_fixtures"), guide_writer="model", draft_writer="model", idea_finder="model", _env_file=None)
    eng = make_engine(st.database_url)
    Base.metadata.create_all(eng)
    factory, write_factory = make_factories(eng)
    ctx = Ctx(st, factory, write_factory=write_factory)
    return create_app(st, ctx), ctx


def _a_write_finishes_while(trigger, entered, release, c, h):
    """Start `trigger` in a thread; once it is inside the slow step, another request must be able to write at once."""
    first = threading.Thread(target=trigger)
    first.start()
    try:
        assert entered.wait(15), "the slow step was never reached"
        done: dict = {}

        def write():
            t0 = time.perf_counter()
            done["r"] = c.post("/api/notes", headers=h, json={"kind": "note", "who": "A customer", "text": "Written while the model is still thinking about something else."})
            done["took"] = time.perf_counter() - t0

        t = threading.Thread(target=write)
        t.start()
        t.join(6)
        assert not t.is_alive(), "a write had to wait for the slow step"
        assert done["r"].status_code == 200 and done["took"] < 5
    finally:
        release.set()
        first.join(30)


def test_building_a_profile_does_not_hold_the_write_lock_while_the_model_answers(tmp_path, monkeypatch):
    from penlark import model_tasks

    entered, release = threading.Event(), threading.Event()

    def slow_guide(llm, stats, name, texts):
        entered.set()
        release.wait(30)
        return model_tasks.Result("Voice guide written by a slow model.", "model", True)

    app, ctx = _model_app(tmp_path)  # the demo seed builds profiles on the way: the slow step is switched on after it
    monkeypatch.setattr(model_tasks, "write_guide", slow_guide)
    with ctx.factory() as s:  # the demo seed locks every profile, and a locked guide is never rewritten by a model
        for p in s.scalars(select(VoiceProfile)):
            p.locked = False
        s.commit()
    c = TestClient(app, base_url="http://api.test")
    h = demo_login(c)
    out: dict = {}
    _a_write_finishes_while(lambda: out.update(r=c.post("/api/profile/build", headers=h, json={"author_id": 1})), entered, release, c, h)
    assert out["r"].status_code == 200 and out["r"].json()["version"] >= 2


def test_writing_a_draft_with_a_model_does_not_hold_the_write_lock_while_it_answers(tmp_path, monkeypatch):
    from penlark import model_tasks

    entered, release = threading.Event(), threading.Event()

    def slow_variants(llm, stats, name, guide_text, idea, kind, n, evaluate, minimum):
        entered.set()
        evaluate("A sentence the re scoring reads from the database.")  # the re scoring has its own session, so it works with no lock held
        release.wait(30)
        return model_tasks.Result([{"label": "Variant A", "text": "Invoices go out the day the work ends.", "note": "slow model"}], "model", True)

    app, ctx = _model_app(tmp_path)
    monkeypatch.setattr(model_tasks, "write_variants", slow_variants)
    c = TestClient(app, base_url="http://api.test")
    h = demo_login(c)
    idea = c.get("/api/ideas", headers=h).json()[0]
    out: dict = {}
    _a_write_finishes_while(lambda: out.update(r=c.post(f"/api/ideas/{idea['id']}/draft", headers=h, json={"author_id": 1, "kind": "post"})), entered, release, c, h)
    assert out["r"].status_code == 200
    assert c.get(f"/api/drafts/{out['r'].json()['id']}", headers=h).json()["text"] == "Invoices go out the day the work ends."


def test_the_idea_finder_does_not_hold_the_write_lock_while_it_works(tmp_path, monkeypatch):
    from penlark import ideas as ideas_mod
    from penlark import jobs

    entered, release = threading.Event(), threading.Event()
    real = ideas_mod.find_ideas

    def slow_find(rows):
        entered.set()
        release.wait(30)
        return real(rows)

    app, ctx = _model_app(tmp_path)
    monkeypatch.setattr(ideas_mod, "find_ideas", slow_find)
    c = TestClient(app, base_url="http://api.test")
    h = demo_login(c)

    def run_job():
        with ctx.write_factory() as s:  # the worker's own kind of session
            jobs.job_ideas(s, ctx)
            s.commit()

    _a_write_finishes_while(run_job, entered, release, c, h)


# ---- 4. a request that waits for the database never blocks the event loop ----

def _while_the_write_lock_is_held(app, call):
    """Hold the SQLite write lock, run `call` in a thread (it must wait for it), and time a /health request meanwhile. The lock is let go after 3 seconds at the latest."""
    holder = app.state.ctx.write_factory()
    holder.execute(select(Draft.id).limit(1))  # BEGIN IMMEDIATE: this session now holds the write lock
    out: dict = {}
    worker = threading.Thread(target=lambda: out.update(r=call()))
    worker.start()
    timer = threading.Timer(3, holder.rollback)
    timer.start()
    try:
        time.sleep(0.5)
        t0 = time.perf_counter()
        out["health"] = app_client_health(app)
        out["took"] = time.perf_counter() - t0
    finally:
        timer.cancel()
        holder.rollback()
        holder.close()
        worker.join(20)
    return out


_CLIENTS: dict = {}


def app_client_health(app):
    return _CLIENTS[id(app)].get("/health").status_code


def test_the_lead_webhook_waiting_for_the_lock_does_not_stall_other_requests(tmp_path):
    import json

    from hardening_helpers import real_settings

    from penlark.attribution import sign

    app = create_app(real_settings(tmp_path))
    body = json.dumps({"lead_ref": "lead-wait", "kind": "lead"}).encode()
    with TestClient(app, base_url="http://api.test") as c:  # one shared event loop, as in the real server
        _CLIENTS[id(app)] = c
        out = _while_the_write_lock_is_held(app, lambda: c.post("/api/webhooks/lead", content=body, headers={"x-penlark-signature": "sha256=" + sign("test-only-lead-secret", body)}))
    assert out["health"] == 200 and out["took"] < 1.5, f"the whole server stood still for {out['took']:.1f} s"
    assert out["r"].status_code == 200 and out["r"].json()["ok"] is True


def test_an_upload_waiting_for_the_lock_does_not_stall_other_requests(tmp_path):
    from hardening_helpers import OWNER, login, real_settings

    app = create_app(real_settings(tmp_path))
    with TestClient(app, base_url="http://api.test") as c:
        _CLIENTS[id(app)] = c
        h = login(c, OWNER)
        aid = c.post("/api/authors", headers=h, json={"name": "Sam Rivera"}).json()["id"]
        out = _while_the_write_lock_is_held(app, lambda: c.post(f"/api/samples/upload?author_id={aid}", headers={**h, "x-filename": "one.txt"}, content=b"Invoices go out on the day the work ends. A short email, a due date, a thank you."))
    assert out["health"] == 200 and out["took"] < 1.5, f"the whole server stood still for {out['took']:.1f} s"
    assert out["r"].status_code == 200 and out["r"].json()["added"] == 1


def test_uploading_into_a_large_library_checks_for_copies_without_reading_every_text_at_once(tmp_path):
    import re
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src" / "penlark" / "service.py").read_text()
    body = src[src.index("def sample_digests"):src.index("def build_profile")]
    assert "yield_per" in body, "the library is read in batches"


# ---- a lead event counts once, even when two arrive together, and an older SQLite file gets the index ----

def test_the_database_refuses_a_second_copy_of_a_lead_event_and_the_webhook_calls_it_a_duplicate(tmp_path):
    import json

    from hardening_helpers import real_settings
    from sqlalchemy.exc import IntegrityError

    from penlark.attribution import sign
    from penlark.models import Conversion

    app = create_app(real_settings(tmp_path))
    ctx = app.state.ctx
    with ctx.factory() as s:
        s.add(Conversion(lead_ref="same", kind="lead", value=0))
        s.commit()
        s.add(Conversion(lead_ref="same", kind="lead", value=0))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
        s.add(Conversion(lead_ref="same", kind="customer", value=0))  # another kind of event for the same lead is a different event
        s.commit()
    # two requests that both passed the "already there?" check: the second insert loses and still answers duplicate
    from penlark.api import routes_public

    body = routes_public.LeadIn(lead_ref="race", kind="lead")
    with ctx.factory() as s, ctx.factory() as other:
        other.add(Conversion(lead_ref="race", kind="lead", value=0))
        other.commit()
        real_first = s.scalars
        calls = {"n": 0}

        def blind(stmt, *a, **k):  # the first look at the conversions finds nothing, as it would if the other request had not committed yet
            calls["n"] += 1
            if calls["n"] == 1:
                return type("Nothing", (), {"first": staticmethod(lambda: None)})()
            return real_first(stmt, *a, **k)

        s.scalars = blind  # type: ignore[method-assign]
        assert routes_public._record_lead(s, ctx, body)["duplicate"] is True


def test_an_older_sqlite_file_gets_the_unique_index_and_loses_its_repeated_events(tmp_path):
    from sqlalchemy import inspect, text

    from penlark.dbsetup import ensure_indexes

    eng = make_engine(f"sqlite:///{tmp_path / 'old.sqlite3'}")
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text("DROP INDEX uq_vp_conversion_lead_kind"))
        for i in range(3):
            c.execute(text("INSERT INTO vp_conversion (lead_ref, kind, value, at) VALUES ('dup', 'lead', 0, '2026-01-01 00:00:00')"))
    assert ensure_indexes(eng) == ["uq_vp_conversion_lead_kind"]
    assert "uq_vp_conversion_lead_kind" in {i["name"] for i in inspect(eng).get_indexes("vp_conversion")}
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM vp_conversion")).scalar() == 1
    assert ensure_indexes(eng) == []  # nothing left to do the second time


# ---- 5. the link guard cannot be fooled by how an address is written ----

@pytest.mark.parametrize("text,found", [
    ("See https://evil.com\\@example.org/x for more", ["https://evil.com\\@example.org/x"]),
    ("See https://example.org@evil.com/x for more", ["https://example.org@evil.com/x"]),
    ("See https://user:pw@example.org/x", ["https://user:pw@example.org/x"]),
    ("Get it at evil.com/free today", ["evil.com/free"]),
    ("Short link: bit.ly/3xYz now", ["bit.ly/3xYz"]),
    ("Short link: t.co/abc and tinyurl.com/x1", ["t.co/abc", "tinyurl.com/x1"]),
    ("Visit evil.com.", ["evil.com"]),
    ("Our page https://example.org/start and example.org/pricing", []),
    ("Our docs at docs.example.org", ["docs.example.org"]),  # a subdomain is not the plain entry
    ("We use Next.js, e.g. for the site, and file.txt stays. Costs 3.5 percent. Works.Then it stops.", []),
    ("Written by Dr.Smith in v1.2.3.", []),
    ("We shipped it.It works. Done.In time.", []),  # a missing space after a full stop
])
def test_the_link_guard_reads_an_address_the_way_a_browser_does(text, found):
    from penlark import service

    st = Settings(redirect_allow_hosts="example.org", public_base_url="http://localhost:3000", _env_file=None)
    assert service.foreign_links(text, st) == found


def test_a_draft_with_a_backslash_link_is_not_ready(client):
    h = demo_login(client)
    ev = client.post("/api/match", headers=h, json={"author_id": 1, "text": "Read the full story at https://evil.com\\@larkspur.example.test/x before you decide anything."}).json()
    assert ev["links"] and ev["ready"] is False


# ---- 6. what a person removes is gone, with every copy of its words the app made ----

def _all_text_of(ctx) -> str:
    """Every stored value in the tables that can hold a person's words, as one string."""
    import json

    from sqlalchemy import select as sel

    from penlark.models import Idea, Sample, Variant

    with ctx.factory() as s:
        parts = [json.dumps(i.evidence) + i.title for i in s.scalars(sel(Idea))]
        parts += [json.dumps(p.examples) + p.guide + json.dumps(p.stats) for p in s.scalars(sel(VoiceProfile))]
        parts += [v.text for v in s.scalars(sel(Variant))] + [d.text + d.title for d in s.scalars(sel(Draft))] + [x.text for x in s.scalars(sel(Sample))] + [n.text for n in s.scalars(sel(Note))]
    return "\n".join(parts)


def test_deleting_a_note_removes_it_and_every_idea_quote_of_it_and_says_which_drafts_still_quote_it(client):
    from penlark.models import Idea

    h = demo_login(client)
    ctx = client.app.state.ctx
    with ctx.factory() as s:
        idea = s.scalars(select(Idea).where(Idea.status == "inbox")).first()
        nid, ev = idea.note_ids[0], [e for e in idea.evidence if e["note_id"] == idea.note_ids[0]]
        quote = ev[0]["quote"]
        only_this = len({e["note_id"] for e in idea.evidence}) == 1
        d = Draft(author_id=1, kind="post", title="Quotes a note", text=f"As a customer told us: {quote}", source_note_ids=[nid], claim_links={"x": nid}, status="approved", created_by="owner@example.test")
        s.add(d)
        s.commit()
        did, iid = d.id, idea.id
    assert client.delete(f"/api/notes/{nid}", headers=demo_login(client, "approver@example.test")).status_code == 403
    assert client.delete(f"/api/notes/{nid}", headers=demo_login(client, "viewer@example.test")).status_code == 403
    r = client.delete(f"/api/notes/{nid}", headers=h)
    assert r.status_code == 200 and did in r.json()["drafts_unlinked"] and did in r.json()["drafts_still_quoting_it"], r.text
    with ctx.factory() as s:
        assert s.get(Note, nid) is None
        assert all(nid not in (i.note_ids or []) and all(e["note_id"] != nid for e in i.evidence) for i in s.scalars(select(Idea)))
        assert (s.get(Idea, iid) is None) == only_this
        d = s.get(Draft, did)
        assert nid not in d.source_note_ids and nid not in d.claim_links.values() and d.status == "draft", "its support changed, so it needs a new approval"
    assert client.delete(f"/api/notes/{nid}", headers=h).status_code == 404
    assert any(e["action"] == "note.deleted" for e in client.get("/api/audit?limit=5", headers=h).json())


def test_deleting_a_sample_removes_its_sentences_from_every_profile_version_and_builds_a_new_one(client):
    from penlark.models import VoiceProfile

    h = demo_login(client)
    ctx = client.app.state.ctx
    with ctx.factory() as s:
        samples = list(s.scalars(select(Sample).where(Sample.author_id == 1)))
        sentences = {x for p in s.scalars(select(VoiceProfile).where(VoiceProfile.author_id == 1)) for v in p.examples.values() for x in v}
        pick = next(x for x in samples if any(t in x.text and not any(t in o.text for o in samples if o.id != x.id) for t in sentences))
        mine = {t for t in sentences if t in pick.text and not any(t in o.text for o in samples if o.id != pick.id)}
        sid, before = pick.id, max(p.version for p in s.scalars(select(VoiceProfile).where(VoiceProfile.author_id == 1)))
    assert mine and all(t in _all_text_of(ctx) for t in mine)
    assert client.delete(f"/api/samples/{sid}", headers=demo_login(client, "approver@example.test")).status_code == 403
    r = client.delete(f"/api/samples/{sid}", headers=h)
    assert r.status_code == 200 and r.json()["profiles_removed"] >= 1 and r.json()["rebuilt_version"] == 1 and r.json()["locked_profile_removed"] is True, r.text
    text = _all_text_of(ctx)
    assert not any(t in text for t in mine), "a sentence of the deleted sample is still stored"
    with ctx.factory() as s:
        assert s.get(Sample, sid) is None and [p.version for p in s.scalars(select(VoiceProfile).where(VoiceProfile.author_id == 1))] == [1]
    assert client.delete(f"/api/samples/{sid}", headers=h).status_code == 404


def test_deleting_a_draft_removes_its_variants_calendar_rows_approval_title_and_exported_file(tmp_path):
    from penlark.models import Variant
    from sendora_core.models import Approval

    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    ex = c.post(f"/api/drafts/{did}/export", headers=h, json={})
    assert ex.status_code == 200
    out = tmp_path / "exports" / ex.json()["external_id"]
    assert out.exists()
    with ctx.factory() as s:
        title = s.get(Draft, did).title
        assert s.scalars(select(Variant).where(Variant.draft_id == did)).first() is not None
    assert c.delete(f"/api/drafts/{did}", headers=demo_login(c, "approver@example.test")).status_code == 403
    r = c.delete(f"/api/drafts/{did}", headers=h)
    assert r.status_code == 200 and r.json()["files_removed"] == 1 and not out.exists()
    with ctx.factory() as s:
        assert s.get(Draft, did) is None and not s.scalars(select(Variant).where(Variant.draft_id == did)).all() and not s.scalars(select(Schedule).where(Schedule.draft_id == did)).all()
        assert all(title not in a.summary for a in s.scalars(select(Approval)))
    assert c.delete(f"/api/drafts/{did}", headers=h).status_code == 404


def test_a_sent_draft_cannot_be_deleted_because_its_record_stops_a_second_send(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    assert _send(c, h, did, as_draft=True).status_code == 200
    r = c.delete(f"/api/drafts/{did}", headers=h)
    assert r.status_code == 409 and "second send" in r.json()["error"]["message"]
    with ctx.factory() as s:
        author = s.get(Draft, did).author_id
    assert c.delete(f"/api/authors/{author}", headers=h).status_code == 409  # a voice with a sent draft stays too
    assert _send(c, h, did).status_code == 409 and len(rec.posts) == 1


def test_deleting_a_voice_removes_its_samples_profiles_and_drafts(client):
    from penlark.models import Draft as D

    h = demo_login(client)
    ctx = client.app.state.ctx
    assert client.delete("/api/authors/1", headers=demo_login(client, "viewer@example.test")).status_code == 403
    r = client.delete("/api/authors/1", headers=h)
    assert r.status_code == 200 and r.json()["samples_removed"] > 0 and r.json()["profiles_removed"] > 0 and r.json()["drafts_removed"] > 0, r.text
    with ctx.factory() as s:
        assert s.get(Author, 1) is None and not s.scalars(select(Sample).where(Sample.author_id == 1)).all()
        assert not s.scalars(select(VoiceProfile).where(VoiceProfile.author_id == 1)).all() and not s.scalars(select(D).where(D.author_id == 1)).all()
    assert client.get("/api/audit/verify", headers=h).json()["ok"] is True


def test_imported_post_numbers_can_be_deleted_one_by_one_or_all_at_once(client):
    from penlark.models import Performance

    h = demo_login(client)
    ctx = client.app.state.ctx
    with ctx.factory() as s:
        ids = list(s.scalars(select(Performance.id)))
    assert len(ids) > 2
    assert client.delete(f"/api/performance/{ids[0]}", headers=demo_login(client, "approver@example.test")).status_code == 403
    assert client.delete(f"/api/performance/{ids[0]}", headers=h).json()["rows"] == 1
    assert client.delete(f"/api/performance/{ids[0]}", headers=h).status_code == 404
    assert client.delete("/api/performance", headers=h).status_code == 400  # needs confirm
    assert client.delete("/api/performance?confirm=true", headers=h).json()["rows"] == len(ids) - 1
    with ctx.factory() as s:
        assert s.scalars(select(Performance.id)).first() is None


# ---- inputs that used to end as an error page ----

def test_a_csv_cell_over_128_kb_is_a_plain_message_not_a_server_error(client):
    h = demo_login(client)
    r = client.post("/api/performance/import", headers=h, json={"csv": "text,impressions\n" + "x" * 200_000 + ",10\n", "preview": True})
    assert r.status_code == 200 and r.json()["ok"] is False and "128 KB" in r.json()["message"]
    r = client.post("/api/performance/import", headers=h, json={"csv": "x" * 200_000 + ",b\n1,2\n", "preview": True})
    assert r.status_code == 200 and r.json()["ok"] is False
    up = client.post("/api/samples/upload?author_id=1", headers={**h, "x-filename": "Shares.csv"}, content=("Date,ShareLink,ShareCommentary\n2026-01-01,x," + "word " * 40_000 + "\n").encode())
    assert up.status_code == 400 and "128 KB" in up.json()["error"]["message"]


def test_an_x_archive_with_texts_that_are_not_text_is_read_for_the_rest(client):
    import json

    h = demo_login(client)
    rows = [{"tweet": {"full_text": 5}}, {"tweet": {"full_text": ["a", "b"]}}, {"tweet": []}, {"tweet": {"full_text": {"a": 1}}}, 7, None,
            {"tweet": {"full_text": "A real post with enough words to count as a sample here", "created_at": "Mon Jan 05 10:00:00 +0000 2026"}}]
    up = client.post("/api/samples/upload?author_id=1", headers={**h, "x-filename": "tweets.js"}, content=("window.YTD.tweets.part0 = " + json.dumps(rows)).encode())
    assert up.status_code == 200 and up.json()["added"] == 1


def test_an_outcome_id_longer_than_its_column_is_refused_with_a_message(tmp_path):
    c, rec, ctx = live_app(tmp_path, status=500)
    h, did = approve_the_waiting_draft(c)
    assert _send(c, h, did).status_code == 502
    r = c.post(f"/api/drafts/{did}/send-outcome", headers=h, json={"posted": True, "external_id": "i" * 121})
    assert r.status_code == 422
    assert c.post(f"/api/drafts/{did}/send-outcome", headers=h, json={"posted": True, "external_id": "i" * 120}).status_code == 200


def test_a_nul_character_in_text_is_taken_out_before_it_is_stored(client):
    import json

    from penlark.attribution import sign

    h = demo_login(client)
    nid = client.post("/api/notes", headers=h, json={"kind": "note", "who": "A\u0000 customer", "text": "Invoices\u0000 go out late every month and nobody notices."}).json()["id"]
    with client.app.state.ctx.factory() as s:
        n = s.get(Note, nid)
        assert "\x00" not in n.text and "\x00" not in n.who and n.text.startswith("Invoices go out")
    body = json.dumps({"lead_ref": "lead\u0000-nul", "kind": "lead"}).encode()
    assert client.post("/api/webhooks/lead", content=body, headers={"x-penlark-signature": "sha256=" + sign("hook-secret-for-tests", body)}).status_code == 200
    from penlark.models import Conversion

    with client.app.state.ctx.factory() as s:
        assert s.scalars(select(Conversion.lead_ref).where(Conversion.lead_ref == "lead-nul")).first() == "lead-nul"
    up = client.post("/api/samples/upload?author_id=1", headers={**h, "x-filename": "a\u0000.txt".encode("latin-1").decode("latin-1")}, content=b"A text with a stray \x00 in it that is long enough to count as one.")
    assert up.status_code == 200


def test_an_email_address_too_long_for_the_log_is_refused_at_start():
    from pydantic import ValidationError

    long = "a" * 70 + "@example.test"
    for field in ("owner_email", "approver_email", "viewer_email"):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{field: long})
    assert Settings(owner_email="a" * 67 + "@example.test", _env_file=None).owner_email.endswith("@example.test")  # exactly 80 is fine


def test_a_tracked_link_that_would_not_fit_its_column_is_refused_with_a_message(client):
    h = demo_login(client)
    r = client.post("/api/links", headers=h, json={"target": "https://larkspur.example.test/?q=" + "\u00e9" * 300, "campaign": "launch"})  # each letter becomes six characters once the address is encoded
    assert r.status_code == 400 and "too long" in r.json()["error"]["message"]


def test_the_text_of_the_settings_never_holds_a_database_password():
    st = Settings(database_url="postgresql+psycopg://penlark:test-only-pw-of-the-database@db:5432/penlark", _env_file=None)
    assert "test-only-pw-of-the-database" not in repr(st) and "test-only-pw-of-the-database" not in str(st)
    assert st.database_url.endswith("/penlark")  # still there for the code that needs it


def test_a_pdf_that_takes_too_long_or_holds_too_much_text_is_refused():
    from penlark import ingest

    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        def __init__(self, pages):
            self.pages = pages

    ticks = iter(range(0, 1000, 7))
    with pytest.raises(ingest.IngestError, match="too long"):
        ingest._pdf_text(Reader([Page("a") for _ in range(10)]), clock=lambda: next(ticks))
    with pytest.raises(ingest.IngestError, match="far more text"):
        ingest._pdf_text(Reader([Page("x" * 1_500_000), Page("x" * 600_000)]), clock=lambda: 0)
    assert ingest._pdf_text(Reader([Page("one"), Page("two")]), clock=lambda: 0) == "one\n\ntwo"


# ---- a proxy the server does not trust is noticed and said out loud ----

def test_requests_through_an_untrusted_proxy_show_a_warning_in_the_settings(client):
    h = demo_login(client)
    assert not [p for p in client.get("/api/settings", headers=h).json()["problems"] if "FORWARDED_ALLOW_IPS" in p]
    for _ in range(6):  # the test client is "testclient"; the header names someone else: the header was not believed
        client.get("/health", headers={"x-forwarded-for": "203.0.113.9"})
    problems = client.get("/api/settings", headers=h).json()["problems"]
    assert any("FORWARDED_ALLOW_IPS" in p and "shares one rate limit" in p for p in problems)


def test_requests_whose_address_is_the_one_in_the_header_show_no_warning(client):
    h = demo_login(client)
    for _ in range(10):
        client.get("/health", headers={"x-forwarded-for": "198.51.100.4, testclient"})
    assert not [p for p in client.get("/api/settings", headers=h).json()["problems"] if "FORWARDED_ALLOW_IPS" in p]
