"""Webhook and upload bodies, the public click route, the kill switch for exports and sends, a real install doing its job, imports, and what the docs and .env.example promise."""

import asyncio
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import DATA, login as demo_login
from hardening_helpers import APPROVER, OWNER, PASSWORD, VIEWER, approve_the_waiting_draft, live_app, login, real_client, real_settings
from penlark import admin, attribution, clock, house_rules
from penlark.api.app import create_app
from penlark.api.routes_public import read_bounded
from penlark.config import Settings
from penlark.models import Author, Click, Conversion, Draft, HouseRule, Schedule
from sendora_core.audit import verify_audit_chain
from sendora_core.settings import BaseAppSettings

ROOT = Path(__file__).resolve().parents[3]


# ---- bodies are read in small pieces and refused as soon as they are too large ----

class FakeRequest:
    """Just enough of a request to watch how much of a body was read."""

    def __init__(self, chunks, declared=None):
        self.headers = {} if declared is None else {"content-length": str(declared)}
        self.chunks, self.read = chunks, 0

    async def stream(self):
        for c in self.chunks:
            self.read += 1
            yield c


def test_a_declared_length_over_the_limit_is_refused_before_any_byte_is_read():
    r = FakeRequest([b"x" * 100] * 50, declared=5000)
    with pytest.raises(HTTPException) as e:
        asyncio.run(read_bounded(r, 1000))
    assert e.value.status_code == 413 and r.read == 0


def test_a_body_with_no_declared_length_is_cut_off_as_it_arrives():
    r = FakeRequest([b"x" * 100] * 1000)
    with pytest.raises(HTTPException) as e:
        asyncio.run(read_bounded(r, 1000))
    assert e.value.status_code == 413 and r.read <= 11  # about ten pieces, not the thousand it could have sent


def test_a_body_at_the_limit_is_read_whole_and_a_bad_length_header_is_refused():
    assert asyncio.run(read_bounded(FakeRequest([b"a" * 500, b"b" * 500], declared=1000), 1000)) == b"a" * 500 + b"b" * 500
    with pytest.raises(HTTPException):
        asyncio.run(read_bounded(FakeRequest([b"x"], declared="abc"), 1000))


def sign(body: bytes, secret="hook-secret-for-tests"):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_the_lead_webhook_refuses_an_endless_body_without_buffering_it(client):
    def endless():
        for _ in range(100000):
            yield b"x" * 1000

    r = client.post("/api/webhooks/lead", content=endless(), headers={"x-penlark-signature": "sha256=00"})
    assert r.status_code == 413


def test_the_lead_webhook_counts_a_repeated_signed_event_once(client):
    body = json.dumps({"lead_ref": "lead-repeat", "kind": "lead"}).encode()
    for _ in range(3):
        assert client.post("/api/webhooks/lead", content=body, headers={"x-penlark-signature": sign(body)}).status_code == 200
    with client.app.state.ctx.factory() as s:
        assert len(list(s.scalars(select(Conversion).where(Conversion.lead_ref == "lead-repeat")))) == 1


def test_a_signature_header_with_a_strange_character_is_a_wrong_signature_not_a_crash(client):
    body = b'{"lead_ref": "x"}'
    r = client.post("/api/webhooks/lead", content=body, headers=[(b"x-penlark-signature", "sha256=\xe9\xe9".encode("latin-1"))])
    assert r.status_code == 401
    assert attribution.verify_signature("secret", body, "\xe9") is False


def test_an_upload_over_8_mb_is_refused_before_it_is_read(client):
    h = {**demo_login(client), "x-filename": "big.txt"}
    r = client.post("/api/samples/upload?author_id=1", headers=h, content=b"a " * 4_000_001)
    assert r.status_code == 413 and "8 MB" in r.json()["error"]["message"]


def test_an_upload_with_the_name_of_a_long_file_still_fits_the_source_column(client):
    h = {**demo_login(client), "x-filename": "n" * 190 + ".txt"}
    assert client.post("/api/samples/upload?author_id=1", headers=h, content=b"A plain file with enough words in it to count as a writing sample.").status_code == 200
    with client.app.state.ctx.factory() as s:
        from penlark.models import Sample

        assert max(len(x.source) for x in s.scalars(select(Sample))) <= 200


# ---- the public click route trusts uvicorn, not the typed header ----

def new_link(client, h):
    return client.post("/api/links", headers=h, json={"target": "https://larkspur.example.test/a", "campaign": "clicks"}).json()["code"]


def test_a_typed_forwarded_for_header_does_not_give_a_click_a_fresh_limit(client):
    code = new_link(client, demo_login(client))
    codes = [client.get(f"/api/public/r/{code}", headers={"x-forwarded-for": f"198.51.{i // 250}.{i % 250 + 1}"}, follow_redirects=False).status_code for i in range(70)]
    assert 429 in codes and codes.count(302) <= 61


def test_a_typed_forwarded_for_header_does_not_make_a_new_visitor(client):
    code = new_link(client, demo_login(client))
    for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        client.get(f"/api/public/r/{code}", headers={"x-forwarded-for": ip, "user-agent": "one browser"}, follow_redirects=False)
    with client.app.state.ctx.factory() as s:
        link_id = client.get("/api/links", headers=demo_login(client)).json()[0]["id"]
        visitors = {c.visitor for c in s.scalars(select(Click)) if c.link_id == link_id}
    assert len(visitors) == 1


# ---- the allow list means exactly what it says ----

@pytest.mark.parametrize("url,allow,ok", [
    ("https://example.com/a", ["example.com"], True),
    ("https://blog.example.com/a", ["example.com"], False),  # a subdomain is a different host unless the list says so
    ("https://blog.example.com/a", ["*.example.com"], True),
    ("https://example.com/a", ["*.example.com"], False),
    ("https://deep.blog.example.com/a", ["*.example.com"], True),
    ("https://evilexample.com/a", ["*.example.com"], False),
    ("https://example.com.evil.org/a", ["example.com"], False),
    ("https://EXAMPLE.com./a", ["Example.com"], True),
    ("https://example.com/a", ["*."], False),
    ("https://example.com/a", [""], False),
])
def test_the_allow_list_matches_the_host_exactly_unless_a_wildcard_is_written(url, allow, ok):
    assert attribution.host_allowed(url, allow) is ok


def test_an_empty_allow_list_allows_nothing_on_a_real_install_and_only_the_demo_host_in_the_demo(tmp_path):
    assert Settings(redirect_allow_hosts="", demo_mode=False, _env_file=None).allow_hosts() == []
    assert Settings(redirect_allow_hosts="", demo_mode=True, _env_file=None).allow_hosts() == ["larkspur.example.test"]
    assert Settings(redirect_allow_hosts="", demo_mode=True, owner_password_hash="x", _env_file=None).allow_hosts() == []
    c = real_client(tmp_path, redirect_allow_hosts="")
    assert c.post("/api/links", headers=login(c), json={"target": "https://larkspur.example.test/a", "campaign": "t"}).status_code == 400


# ---- the owner's switches in the app are read from the database ----

def test_the_kill_switch_stops_the_file_export_and_every_send_even_with_mode_live(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    assert c.post("/api/settings", headers=h, json={"kill_switch": True}).status_code == 200  # set in the app, not in the environment
    r = c.post(f"/api/drafts/{did}/export", headers=h, json={})
    assert r.status_code == 409 and "kill switch" in r.json()["error"]["message"]
    assert not list(Path(ctx.settings.export_dir).glob("*"))
    assert c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False}).status_code == 409
    assert rec.posts == []
    c.post("/api/settings", headers=h, json={"kill_switch": False})
    assert c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False}).status_code == 200
    assert len(rec.posts) == 1


def test_the_draft_mode_switch_in_the_app_stops_a_send_with_mode_live_but_not_the_file_export(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    c.post("/api/settings", headers=h, json={"force_draft": True})
    r = c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False})
    assert r.status_code == 409 and "draft" in r.json()["error"]["message"].lower() and rec.posts == []
    assert c.post(f"/api/drafts/{did}/export", headers=h, json={}).status_code == 200  # the file export is the way out in draft mode: it sends nothing anywhere


def test_the_kill_switch_in_the_environment_also_stops_the_export(tmp_path):
    c, rec, ctx = live_app(tmp_path, kill_switch=True)
    h, did = approve_the_waiting_draft(c)
    assert c.post(f"/api/drafts/{did}/export", headers=h, json={}).status_code == 409


# ---- a send happens once, and says so when the vendor failed ----

def body(**kw):
    return {"channel_id": "ch-1", "confirm": True, "as_draft": False, **kw}


def test_a_draft_saved_at_the_scheduler_is_not_sent_a_second_time(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    assert c.post(f"/api/drafts/{did}/send", headers=h, json=body(as_draft=True)).status_code == 200
    again = c.post(f"/api/drafts/{did}/send", headers=h, json=body())
    assert again.status_code == 409 and "already sent" in again.json()["error"]["message"] and len(rec.posts) == 1


def test_a_draft_that_is_being_sent_cannot_be_sent_edited_or_exported(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    with ctx.factory() as s:
        s.get(Draft, did).status = "sending"
        s.commit()
    assert c.post(f"/api/drafts/{did}/send", headers=h, json=body()).status_code == 409
    assert c.put(f"/api/drafts/{did}", headers=h, json={"text": "Changed words while the first send is still out there."}).status_code == 409
    assert c.post(f"/api/drafts/{did}/export", headers=h, json={}).status_code == 409
    assert rec.posts == []


def test_a_send_that_never_finished_is_released_after_half_an_hour_and_the_audit_log_says_so(tmp_path):
    from datetime import timedelta

    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    with ctx.factory() as s:
        d = s.get(Draft, did)
        d.status, d.updated_at = "sending", clock.DEMO_START - timedelta(minutes=5)
        s.commit()
    assert c.post(f"/api/drafts/{did}/export", headers=h, json={}).status_code == 409  # five minutes ago: still held
    with ctx.factory() as s:
        s.get(Draft, did).updated_at = clock.DEMO_START - timedelta(minutes=45)
        s.commit()
    assert c.post(f"/api/drafts/{did}/export", headers=h, json={}).status_code == 200
    assert any(e["action"] == "draft.send_released" for e in c.get("/api/audit?limit=20", headers=h).json())


def test_a_vendor_error_is_said_plainly_nothing_is_recorded_as_sent_and_the_draft_goes_back(tmp_path):
    c, rec, ctx = live_app(tmp_path, status=500)
    h, did = approve_the_waiting_draft(c)
    r = c.post(f"/api/drafts/{did}/send", headers=h, json=body())
    assert r.status_code == 502 and "check postiz" in r.json()["error"]["message"].lower()
    with ctx.factory() as s:
        assert s.get(Draft, did).status == "approved" and not list(s.scalars(select(Schedule).where(Schedule.status == "sent")))
    assert any(e["action"] == "draft.send_failed" for e in c.get("/api/audit?limit=5", headers=h).json())


def test_a_send_checks_its_fields(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    assert c.post(f"/api/drafts/{did}/send", headers=h, json=body(platform="myspace")).status_code == 422
    assert c.post(f"/api/drafts/{did}/send", headers=h, json=body(run_on="2026-13-45")).status_code == 400
    assert c.post(f"/api/drafts/{did}/send", headers=h, json=body(run_on="soon")).status_code == 422
    assert rec.posts == [] and c.get(f"/api/drafts/{did}", headers=h).json()["status"] == "approved"


def test_a_send_never_changes_the_shared_adapter(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    original = ctx.scheduler.s
    c.post("/api/settings", headers=h, json={"kill_switch": True})
    c.post(f"/api/drafts/{did}/send", headers=h, json=body())
    assert ctx.scheduler.s is original and original.kill_switch is False  # the switch was read for that one request only


def test_the_changes_that_matter_are_in_the_audit_log(client):
    h = demo_login(client)
    idea = client.get("/api/ideas", headers=h).json()[0]
    client.post(f"/api/ideas/{idea['id']}/drop", headers=h)
    rid = client.post("/api/rules", headers=h, json={"kind": "phrase", "value": "synergise", "note": "x"}).json()["id"]
    client.delete(f"/api/rules/{rid}", headers=h)
    eid = client.post("/api/experiments", headers=h, json={"name": "Hook test"}).json()["id"]
    client.put(f"/api/experiments/{eid}", headers=h, json={"a_n": 10, "a_hits": 2, "b_n": 10, "b_hits": 3})
    h2, did = approve_the_waiting_draft(client)
    sid = client.post(f"/api/drafts/{did}/schedule", headers=h, json={"platform": "linkedin", "run_on": "2026-12-05"}).json()["id"]
    client.delete(f"/api/schedule/{sid}", headers=h)
    actions = {e["action"] for e in client.get("/api/audit?limit=200", headers=h).json()}
    assert {"idea.dropped", "rule.deleted", "experiment.created", "experiment.updated", "schedule.removed"} <= actions


# ---- a real install does the whole job from an empty database ----

def test_a_real_install_starts_with_the_built_in_rules_and_keeps_a_switched_off_one_off(tmp_path):
    s1 = real_settings(tmp_path)
    c = TestClient(create_app(s1))
    n = len(c.get("/api/rules", headers=login(c)).json()["rules"])
    assert n == len(house_rules.DEFAULT_BANNED) + len(house_rules.DEFAULT_PATTERNS)
    rid = c.get("/api/rules", headers=login(c)).json()["rules"][0]["id"]
    c.put(f"/api/rules/{rid}", headers=login(c), json={"enabled": False})
    c2 = TestClient(create_app(s1))  # a second start on the same database adds nothing and does not switch the rule back on
    rules = c2.get("/api/rules", headers=login(c2)).json()["rules"]
    assert len(rules) == n and next(r for r in rules if r["id"] == rid)["enabled"] is False


def test_a_real_install_does_the_core_job_from_an_empty_database(tmp_path):
    c = real_client(tmp_path)
    owner, approver, viewer = login(c, OWNER), login(c, APPROVER), login(c, VIEWER)
    assert c.get("/api/authors", headers=owner).json() == []
    assert c.post("/api/authors", headers=viewer, json={"name": "Sam Rivera"}).status_code == 403
    assert c.post("/api/authors", headers=owner, json={"name": "S"}).status_code == 422
    made = c.post("/api/authors", headers=owner, json={"name": "Sam Rivera", "about": "Runs a small bookkeeping firm."}).json()
    assert made["slug"] == "sam-rivera"
    assert c.post("/api/authors", headers=owner, json={"name": " sam rivera "}).status_code == 409
    assert c.post("/api/authors", headers=owner, json={"name": "Sam-Rivera"}).json()["slug"] == "sam-rivera-2"
    aid = made["id"]
    for i, text in enumerate(json.loads((Path(DATA) / "seed" / "samples_tobias.json").read_text())[:6]):
        assert c.post("/api/samples", headers=owner, json={"author_id": aid, "text": text, "kind": "text"}).status_code == 200, i
    pid = c.post("/api/profile/build", headers=owner, json={"author_id": aid}).json()["id"]
    assert c.post(f"/api/profile/{pid}/lock", headers=owner).status_code == 200
    notes = json.loads((Path(DATA) / "seed" / "notes.json").read_text())[:6]
    for n in notes:
        assert c.post("/api/notes", headers=owner, json={"kind": n["kind"], "who": "A customer", "text": n["text"]}).status_code == 200
    assert c.post("/api/ideas/refresh", headers=owner).json()["ideas"] >= 1
    idea = c.get("/api/ideas", headers=owner).json()[0]
    did = c.post(f"/api/ideas/{idea['id']}/draft", headers=owner, json={"author_id": aid, "kind": "post"}).json()["id"]
    clean = "Invoices go out on the day the work ends. Short email, due date first, a thank you at the end."
    assert c.put(f"/api/drafts/{did}", headers=owner, json={"text": clean}).status_code == 200
    ask = c.post(f"/api/drafts/{did}/request-approval", headers=owner)
    assert ask.status_code == 200, ask.text
    ap = next(a for a in c.get("/api/approvals", headers=owner).json() if a["status"] == "pending")
    assert c.post(f"/api/approvals/{ap['id']}/decide", headers=owner, json={"approve": True}).status_code == 409  # the asker cannot approve
    assert c.post(f"/api/approvals/{ap['id']}/decide", headers=approver, json={"approve": True, "text_sha256": ap["preview"]["text_sha256"]}).status_code == 200
    ex = c.post(f"/api/drafts/{did}/export", headers=owner, json={})
    assert ex.status_code == 200 and re.fullmatch(rf"draft-{did}-linkedin-.+\.txt", ex.json()["external_id"])
    assert (tmp_path / "exports" / ex.json()["external_id"]).read_text().strip() == clean
    assert c.get("/api/audit/verify", headers=owner).json()["ok"] is True


def test_a_voice_can_be_added_from_the_command_line(tmp_path, capsys):
    st = real_settings(tmp_path)
    assert admin.main(["add-voice", "Sam Rivera", "--about", "Bookkeeper"], settings=st) == 0
    assert "sam-rivera" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="already a voice"):
        admin.main(["add-voice", "sam rivera"], settings=st)
    assert admin.main(["builtin-rules"], settings=st) == 0 and "Built in rules saved" in capsys.readouterr().out
    c = TestClient(create_app(st))
    assert [a["name"] for a in c.get("/api/authors", headers=login(c)).json()] == ["Sam Rivera"]
    with c.app.state.ctx.factory() as s:
        assert verify_audit_chain(s)[0] is True and len(list(s.scalars(select(Author)))) == 1


def test_the_demo_still_has_its_three_voices_and_the_rules(client):
    h = demo_login(client)
    assert len(client.get("/api/authors", headers=h).json()) == 3
    with client.app.state.ctx.factory() as s:
        rows = list(s.scalars(select(HouseRule)))
        assert len(rows) == len({(r.kind, r.value) for r in rows})  # no rule twice


# ---- every import path in the docs works ----

def upload(c, h, name, data, aid=1):
    return c.post(f"/api/samples/upload?author_id={aid}", headers={**h, "x-filename": name}, content=data)


def test_every_file_type_the_docs_name_can_be_imported(client):
    h = demo_login(client)
    posts = "\n".join(f'2026-01-0{i},https://x.test/{i},"{"A real sentence about invoices and clients and how late payments feel " * 2} number {i}",,,PUBLIC' for i in range(1, 4))
    shares = "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,Visibility\n" + posts
    assert upload(client, h, "Shares.csv", shares.encode()).json()["added"] == 3
    tweets = "window.YTD.tweets.part0 = " + json.dumps([{"tweet": {"full_text": f"Tweet number {i} says something about invoices that is long enough to keep", "created_at": "Mon Jan 01 10:00:00 +0000 2026"}} for i in range(3)])
    assert upload(client, h, "tweets.js", tweets.encode()).json()["added"] == 3
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello and welcome to this short talk about sending invoices on time.\n\n00:00:05.000 --> 00:00:09.000\nThe first thing I tell every client is to send the invoice the same day."
    assert upload(client, h, "talk.vtt", vtt.encode()).json()["added"] == 1
    assert upload(client, h, "notes.md", b"# A note\n\nSome [linked](https://x.test) writing of mine that is long enough to keep as a sample.").json()["added"] == 1
    assert upload(client, h, "post.txt", b"A plain text post of mine with enough words in it to count as a writing sample.").json()["added"] == 1
    assert upload(client, h, "broken.pdf", b"%PDF-1.4 not really").status_code == 400
    csv = "Date,Views,Reactions,Content\n2026-02-01,1000,50,A post with some words in it for the numbers\n"
    assert client.post("/api/performance/import", headers=h, json={"csv": csv, "preview": False}).json()["rows"] == 1


def tiny_pdf(text: str) -> bytes:
    """A one page PDF with a real text layer, with a correct cross reference table (written by hand so the test needs no PDF library to write one)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
               b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
               b"<</Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream", b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    out, offsets = b"%PDF-1.4\n", []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    return out + f"trailer\n<</Root 1 0 R/Size {len(objects) + 1}>>\nstartxref\n{xref}\n%%EOF\n".encode()


def test_a_pdf_with_text_is_read(client):
    r = upload(client, demo_login(client), "mine.pdf", tiny_pdf("A short PDF page of my own writing, long enough to keep."))
    assert r.status_code == 200 and r.json()["added"] == 1


# ---- the calendar day, identity and the version ----

def test_today_follows_the_timezone_setting(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda session, demo: datetime(2026, 12, 1, 23, 30, tzinfo=UTC))
    c = real_client(tmp_path, timezone="Pacific/Auckland")
    with c.app.state.ctx.factory() as s:
        assert c.app.state.ctx.today(s).isoformat() == "2026-12-02"  # it is already tomorrow in New Zealand
    other = tmp_path / "utc"
    other.mkdir()
    c2 = real_client(other, timezone="UTC")
    with c2.app.state.ctx.factory() as s:
        assert c2.app.state.ctx.today(s).isoformat() == "2026-12-01"


def test_an_unknown_timezone_is_refused():
    with pytest.raises(ValueError, match="timezone"):
        Settings(timezone="Mars/Olympus", _env_file=None)


def test_the_placeholders_are_listed_and_stop_a_live_install(tmp_path):
    st = real_settings(tmp_path, owner_email="owner@example.test", redirect_allow_hosts="", public_base_url="http://localhost:3000")
    problems = st.problems()
    assert any("OWNER_EMAIL" in p for p in problems) and any("REDIRECT_ALLOW_HOSTS" in p for p in problems) and any("PUBLIC_BASE_URL" in p for p in problems)
    assert real_settings(tmp_path, mode="live").runtime_errors() == []
    assert any("OWNER_EMAIL" in p for p in real_settings(tmp_path, mode="live", owner_email="owner@example.test").runtime_errors())
    assert real_settings(tmp_path, owner_email="owner@example.test").runtime_errors() == []  # in draft mode the example address only shows up as a problem


def test_the_version_is_the_same_everywhere(tmp_path):
    version = real_client(tmp_path).app.version
    assert version == "1.0.1"
    assert f'version = "{version}"' in (ROOT / "apps/api/pyproject.toml").read_text()
    assert json.loads((ROOT / "package.json").read_text())["version"] == version
    assert json.loads((ROOT / "apps/web/package.json").read_text())["version"] == version
    assert (ROOT / "CHANGELOG.md").read_text().split("## ")[1].startswith(f"{version} (2026-11-25)")


# ---- .env.example and the docs list every setting ----

def every_setting() -> set[str]:
    return {n.upper() for n in Settings.model_fields} | {n.upper() for n in BaseAppSettings.model_fields}


def example_names() -> set[str]:
    return {m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", (ROOT / ".env.example").read_text(), re.M)}


def test_env_example_lists_every_setting():
    missing = sorted(every_setting() - example_names())
    assert not missing, f"add these to .env.example: {missing}"


def test_the_environment_variables_doc_lists_every_setting():
    doc = (ROOT / "docs" / "04-ENVIRONMENT-VARIABLES.md").read_text()
    headings = " ".join(re.findall(r"^## (.+)$", doc, re.M))
    listed = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", doc)) | set(re.findall(r"[A-Z][A-Z0-9_]{2,}", headings))
    missing = sorted(every_setting() - listed)
    assert not missing, f"add these to docs/04-ENVIRONMENT-VARIABLES.md: {missing}"


def test_env_example_loads_as_it_is_and_is_not_a_demo():
    s = Settings(_env_file=str(ROOT / ".env.example"))
    assert s.demo_mode is False and s.demo_shortcuts is False and s.owner_password_hash is None and s.llm_call_budget is None and s.redirect_allow_hosts == ""


def test_the_example_secret_is_refused_so_nobody_can_run_the_example_as_it_is():
    s = Settings(_env_file=str(ROOT / ".env.example"))
    assert any("SESSION_SECRET" in p for p in s.runtime_errors())


# ---- a link in a draft is a deliberate choice ----

@pytest.mark.parametrize("text,found", [
    ("Read this: https://evil.example.net/pay now", ["https://evil.example.net/pay"]),
    ("Go to www.evil.example.net.", ["www.evil.example.net"]),
    ("Write to pay@evil.example.net for details", ["pay@evil.example.net"]),
    ("Our page https://larkspur.example.test/start and https://blog.larkspur.example.test/x", ["https://blog.larkspur.example.test/x"]),  # a subdomain is not the plain entry
    ("A plain sentence with no link at all, only 3.5 percent.", []),
    ("Tracked: http://localhost:3000/r/abc23", []),  # the host of PUBLIC_BASE_URL is the owner's
])
def test_links_and_addresses_that_are_not_the_owners_are_found(text, found):
    from penlark import service

    st = Settings(redirect_allow_hosts="larkspur.example.test", public_base_url="http://localhost:3000", _env_file=None)
    assert service.foreign_links(text, st) == found


def test_a_draft_with_a_foreign_link_is_not_ready_and_says_why(client):
    h = demo_login(client)
    r = client.post("/api/match", headers=h, json={"author_id": 1, "text": "Invoices go out on the day the work ends. Pay here: https://evil.example.net/pay"}).json()
    assert r["links"] == ["https://evil.example.net/pay"] and r["ready"] is False
    from penlark import service

    assert "not yours" in service.readiness_problem({"placeholders": [], "links": r["links"], "rules": {"unsupported_claims": [], "style": []}, "match": {"score": 99}}, 60)
