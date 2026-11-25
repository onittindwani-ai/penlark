import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

from conftest import DATA, login
from penlark import attribution


def hdr(c, email="owner@example.test"):
    return login(c, email)


def test_every_route_needs_a_session_except_login_redirect_and_webhook(client):
    for path in ("/api/overview", "/api/drafts", "/api/ideas", "/api/performance", "/api/audit"):
        assert client.get(path).status_code == 401
    assert client.get("/api/public/r/nope123").status_code == 404
    assert client.post("/api/webhooks/lead", content=b"{}").status_code == 401
    assert client.get("/health").status_code == 200


def test_login_rate_limit_and_wrong_password(client):
    assert client.post("/api/auth/login", json={"email": "owner@example.test", "password": "wrong"}).status_code == 401
    codes = {client.post("/api/auth/login", json={"email": "x@example.test", "password": "bad"}).status_code for _ in range(8)}
    assert 429 in codes


def test_overview_ideas_and_profile_are_seeded(client):
    h = hdr(client)
    o = client.get("/api/overview", headers=h).json()
    assert o["posts"] == 60 and o["pending_approvals"] == 1 and o["ideas_inbox"] >= 2
    authors = client.get("/api/authors", headers=h).json()
    assert [a["slug"] for a in authors] == ["tobias", "imani", "gareth"] and all(a["locked"] for a in authors)
    p = client.get(f"/api/profile?author_id={authors[0]['id']}", headers=h).json()
    assert len(p["profile"]["radar"]) == 14 and p["profile"]["guide"] and p["profile"]["examples"]


def test_live_match_endpoint_scores_and_flags(client):
    h = hdr(client)
    r = client.post("/api/match", headers=h, json={"author_id": 1, "text": "Let's dive in — it's a game changer. I grew sales by 300 percent."}).json()
    assert r["match"]["score"] < 80 and r["rules"]["style"] and r["rules"]["unsupported_claims"] and not r["ready"]


def test_draft_cannot_be_approved_by_the_person_who_asked(client):
    h = hdr(client)
    ap = client.get("/api/approvals", headers=h).json()
    pending = next(a for a in ap if a["status"] == "pending")
    r = client.post(f"/api/approvals/{pending['id']}/decide", headers=h, json={"approve": True})
    assert r.status_code == 409 and "someone else must decide" in r.json()["error"]["message"]
    h2 = hdr(client, "approver@example.test")
    assert client.post(f"/api/approvals/{pending['id']}/decide", headers=h2, json={"approve": True}).status_code == 200
    d = client.get(f"/api/drafts/{pending['payload']['draft_id']}", headers=h).json()
    assert d["status"] == "approved"


def test_request_approval_refuses_brackets_and_unsupported_claims_then_works(client):
    h = hdr(client)
    drafts = client.get("/api/drafts?status=draft", headers=h).json()
    d = drafts[0]
    assert client.post(f"/api/drafts/{d['id']}/request-approval", headers=h).status_code == 409  # brackets are still there
    clean = "Invoices go out on the day the work ends. Short email, due date first, a thank you at the end."
    assert client.put(f"/api/drafts/{d['id']}", headers=h, json={"text": clean}).status_code == 200
    assert client.post(f"/api/drafts/{d['id']}/request-approval", headers=h).status_code == 200
    again = client.put(f"/api/drafts/{d['id']}", headers=h, json={"text": "Invoices go out on the day the work ends. I grew sales by 300 percent."}).json()
    assert again["status"] == "draft"  # an edit voids the approval request
    assert client.post(f"/api/drafts/{d['id']}/request-approval", headers=h).status_code == 409


def test_only_approved_drafts_reach_the_calendar_and_export_never_sends(client, tmp_path):
    h = hdr(client)
    d = client.get("/api/drafts?status=draft", headers=h).json()[0]
    assert client.post(f"/api/drafts/{d['id']}/schedule", headers=h, json={"run_on": "2026-12-05"}).status_code == 409
    assert client.post(f"/api/drafts/{d['id']}/export", headers=h, json={"platform": "linkedin"}).status_code == 409
    pend = next(a for a in client.get("/api/approvals", headers=h).json() if a["status"] == "pending")
    client.post(f"/api/approvals/{pend['id']}/decide", headers=hdr(client, "approver@example.test"), json={"approve": True})
    did = pend["payload"]["draft_id"]
    s = client.post(f"/api/drafts/{did}/schedule", headers=h, json={"platform": "linkedin", "run_on": "2026-12-05"})
    assert s.status_code == 200
    assert client.post(f"/api/drafts/{did}/schedule", headers=h, json={"run_on": "2026-13-45"}).status_code in (400, 422)
    sid = s.json()["id"]
    assert client.put(f"/api/schedule/{sid}", headers=h, json={"run_on": "2026-12-09"}).json()["from"] == "2026-12-05"
    e = client.post(f"/api/drafts/{did}/export", headers=h, json={"platform": "linkedin"})
    assert e.status_code == 200 and "Copy it" in e.json()["detail"]
    assert client.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "c1", "confirm": True}).status_code == 409  # export adapter never sends


def test_tracked_link_allow_list_and_redirect(client):
    h = hdr(client)
    bad = client.post("/api/links", headers=h, json={"target": "https://evil.example.org/x", "campaign": "t"})
    assert bad.status_code == 400
    for evil in ("javascript:alert(1)", "http://larkspur.example.test/x", "https://larkspur.example.test.evil.org/x", "https://user:pw@larkspur.example.test/x", "//evil.org"):
        assert client.post("/api/links", headers=h, json={"target": evil, "campaign": "t"}).status_code == 400, evil
    ok = client.post("/api/links", headers=h, json={"target": "https://larkspur.example.test/start?utm_source=old", "campaign": "Invoice Timing", "source": "LinkedIn"})
    assert ok.status_code == 200 and "utm_campaign=invoice-timing" in ok.json()["target"] and "utm_source=old" not in ok.json()["target"]
    code = ok.json()["code"]
    r = client.get(f"/api/public/r/{code}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://larkspur.example.test/start") and r.headers["cache-control"] == "no-store"
    assert client.get("/api/public/r/" + "a" * 40, follow_redirects=False).status_code == 404
    clicks = client.get("/api/attribution", headers=h).json()["totals"]["clicks"]
    assert clicks > 0


def test_redirect_target_never_comes_from_the_request(client):
    h = hdr(client)
    code = client.post("/api/links", headers=h, json={"target": "https://larkspur.example.test/a", "campaign": "t"}).json()["code"]
    r = client.get(f"/api/public/r/{code}?url=https://evil.org&next=https://evil.org", headers={"referer": "https://evil.org"}, follow_redirects=False)
    assert r.headers["location"].startswith("https://larkspur.example.test/")


def test_redirect_stops_when_the_allow_list_changes(client):
    h = hdr(client)
    code = client.post("/api/links", headers=h, json={"target": "https://larkspur.example.test/a", "campaign": "t"}).json()["code"]
    client.app.state.ctx.settings.redirect_allow_hosts = "other.example.test"
    assert client.get(f"/api/public/r/{code}", follow_redirects=False).status_code == 410


@settings(max_examples=80, deadline=None)
@given(st.text(max_size=80))
def test_property_no_url_outside_the_allow_list_is_ever_accepted(url):
    allow = ["larkspur.example.test"]
    if attribution.host_allowed(url, allow):
        from urllib.parse import urlparse

        h = urlparse(url).hostname
        assert h == "larkspur.example.test" or h.endswith(".larkspur.example.test")


def sign(body: bytes, secret="hook-secret-for-tests"):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_lead_webhook_signature_dedupe_and_attribution(client):
    h = hdr(client)
    code = client.get("/api/links", headers=h).json()[0]["code"]
    body = json.dumps({"lead_ref": "lead-x1", "kind": "lead", "link_code": code}).encode()
    assert client.post("/api/webhooks/lead", content=body).status_code == 401
    assert client.post("/api/webhooks/lead", content=body, headers={"x-penlark-signature": sign(body, "wrong")}).status_code == 401
    ok = client.post("/api/webhooks/lead", content=body, headers={"x-penlark-signature": sign(body)})
    assert ok.status_code == 200 and ok.json()["attributed"] is True
    assert client.post("/api/webhooks/lead", content=body, headers={"x-penlark-signature": sign(body)}).json()["duplicate"] is True
    assert client.post("/api/webhooks/lead", content=b"x" * 20000, headers={"x-penlark-signature": sign(b"x" * 20000)}).status_code == 413


def test_csv_import_preview_then_save(client):
    h = hdr(client)
    csv = "Date,Views,Reactions,Content\n2026-02-01,1000,50,A post with some words in it\n"
    prev = client.post("/api/performance/import", headers=h, json={"csv": csv, "preview": True}).json()
    assert prev["ok"] and prev["rows"] == 1 and not prev["saved"]
    before = len(client.get("/api/performance", headers=h).json())
    client.post("/api/performance/import", headers=h, json={"csv": csv, "preview": False})
    assert len(client.get("/api/performance", headers=h).json()) == before + 1
    bad = client.post("/api/performance/import", headers=h, json={"csv": "a,b\n1,2"}).json()
    assert bad["ok"] is False and "Map these columns" in bad["message"]


def test_house_rules_crud_and_builtin_protection(client):
    h = hdr(client)
    r = client.post("/api/rules", headers=h, json={"kind": "phrase", "value": "synergize"}).json()
    assert client.post("/api/match", headers=h, json={"author_id": 1, "text": "We synergize quickly."}).json()["rules"]["style"]
    client.put(f"/api/rules/{r['id']}", headers=h, json={"enabled": False})
    assert not client.post("/api/match", headers=h, json={"author_id": 1, "text": "We synergize quickly."}).json()["rules"]["style"]
    assert client.delete(f"/api/rules/{r['id']}", headers=h).status_code == 200
    builtin = next(x for x in client.get("/api/rules", headers=h).json()["rules"] if x["builtin"])
    assert client.delete(f"/api/rules/{builtin['id']}", headers=h).status_code == 409
    assert client.post("/api/rules", headers=h, json={"kind": "pattern", "value": "(unclosed"}).status_code == 400


def test_profile_lock_and_new_version_diff(client):
    h = hdr(client)
    prof = client.get("/api/profile?author_id=1", headers=h).json()["profile"]
    assert client.put(f"/api/profile/{prof['id']}/guide", headers=h, json={"guide": "x"}).status_code == 409  # locked
    client.post("/api/samples", headers=h, json={"author_id": 1, "text": "A long, flowing, formal sentence that wanders on and on, with many clauses; it is, furthermore, unlike the rest."})
    b = client.post("/api/profile/build", headers=h, json={"author_id": 1}).json()
    assert b["version"] == 2
    assert client.put(f"/api/profile/{b['id']}/guide", headers=h, json={"guide": "My own words."}).status_code == 200
    assert client.post(f"/api/profile/{b['id']}/lock", headers=h).status_code == 200


def test_upload_rejects_bad_files_with_a_clear_message(client):
    h = {**hdr(client), "x-filename": "broken.pdf"}
    r = client.post("/api/samples/upload?author_id=1", headers=h, content=b"%PDF-1.4 not really")
    assert r.status_code == 400 and "PDF" in r.json()["error"]["message"]
    ok = client.post("/api/samples/upload?author_id=1", headers={**h, "x-filename": "notes.md"}, content=b"# Hi\n\nSome writing of mine that is long enough to keep.")
    assert ok.json()["added"] == 1


def test_experiment_results_and_validation(client):
    h = hdr(client)
    ex = client.get("/api/experiments", headers=h).json()
    assert {e["result"]["verdict"] for e in ex} == {"difference", "too_small"}
    assert client.put(f"/api/experiments/{ex[0]['id']}", headers=h, json={"a_n": 10, "a_hits": 11, "b_n": 10, "b_hits": 1}).status_code == 400


def test_kill_switch_and_audit_chain(client):
    h = hdr(client)
    assert client.post("/api/settings", headers=h, json={"kill_switch": True}).json()["kill_switch"] is True
    assert client.get("/api/audit/verify", headers=h).json()["ok"] is True


def test_demo_routes_exist_only_in_demo_mode(tmp_path):
    from penlark.api.app import create_app
    from penlark.config import Settings

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path/'p.sqlite3'}", session_secret="Rt7Kq2Vw9Xm4Zc8Lb3Nf6Hy1Js5Dp0Ga2Ue7Tq4Wi9", demo_mode=False, owner_password_hash=None, _env_file=None))
    c = TestClient(app)
    assert c.post("/api/demo/reset").status_code in (401, 404)


def test_viewer_reads_everything_and_changes_nothing(client):
    viewer, owner = hdr(client, "viewer@example.test"), hdr(client)
    assert client.get("/api/auth/me", headers=viewer).json()["role"] == "viewer"
    for path in ("/api/overview", "/api/drafts", "/api/ideas", "/api/approvals", "/api/schedule", "/api/rules", "/api/settings"):
        assert client.get(path, headers=viewer).status_code == 200, path
    ap = next(a for a in client.get("/api/approvals", headers=owner).json() if a["status"] == "pending")
    assert client.post(f"/api/approvals/{ap['id']}/decide", headers=viewer, json={"approve": True}).status_code == 403
    assert client.post("/api/rules", headers=viewer, json={"kind": "phrase", "value": "synergy"}).status_code == 403
    assert client.post("/api/settings", headers=viewer, json={"kill_switch": True}).status_code == 403


def test_a_second_person_decides_and_the_asker_is_refused_by_the_base(client):
    owner, approver = hdr(client), hdr(client, "approver@example.test")
    ap = next(a for a in client.get("/api/approvals", headers=owner).json() if a["status"] == "pending")
    assert ap["requested_by"] != "approver@example.test"
    own = client.post(f"/api/approvals/{ap['id']}/decide", headers=owner, json={"approve": True})
    assert own.status_code == 409 and "someone else must decide" in own.json()["error"]["message"]
    assert client.post(f"/api/approvals/{ap['id']}/decide", headers=approver, json={"approve": True}).status_code == 200


def test_default_model_backend_is_the_offline_stand_in(client):
    ctx = client.app.state.ctx
    from penlark.offline_llm import OfflineBackend

    with ctx.factory() as s:
        llm = ctx.llm(s)
    assert isinstance(llm.backend, OfflineBackend) and not llm.backend.is_live
    assert client.get("/api/settings", headers=hdr(client)).json()["writer"].startswith("offline templates")


def test_login_burst_setting_raises_the_sign_in_limit(tmp_path):
    from penlark.api.app import create_app
    from penlark.config import Settings

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'b.sqlite3'}", session_secret="test-secret-test-secret", seed_dir=DATA, login_burst=50, _env_file=None))
    c = TestClient(app)
    codes = {c.post("/api/auth/login", json={"email": "x@example.test", "password": "bad"}).status_code for _ in range(20)}
    assert codes == {401}
