"""An approval is for the exact words that were shown: the whole text, a fingerprint of it, and a refusal if one character changes afterwards."""

import hashlib

from sqlalchemy import select

from conftest import login
from hardening_helpers import approve_the_waiting_draft, live_app
from penlark import service
from penlark.models import Draft, Schedule
from sendora_core.approvals import request_approval
from sendora_core.models import Approval

LONG = ("Invoices go out on the day the work ends. " * 130).strip()  # about 5,500 characters


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pending(c, h):
    return next(a for a in c.get("/api/approvals", headers=h).json() if a["status"] == "pending")


def test_the_approver_sees_every_character_of_a_long_draft(client):
    h = login(client)
    with client.app.state.ctx.factory() as s:
        d = Draft(author_id=1, kind="newsletter", title="Long one", text=LONG, created_by="owner@example.test")
        s.add(d)
        s.flush()
        a = request_approval(s, "draft.approve", "Approve draft: Long one", {"draft_id": d.id, "text_sha256": service.text_digest(LONG)}, "medium", "owner@example.test")
        d.status, d.approval_id = "pending_approval", a.id
        s.commit()
        wanted = a.id
    row = next(x for x in client.get("/api/approvals", headers=h).json() if x["id"] == wanted)
    assert len(LONG) > 1200 and row["preview"]["text"] == LONG and row["preview"]["truncated"] is False
    assert row["preview"]["text_sha256"] == digest(LONG) == row["preview"]["approved_text_sha256"]


def test_a_decided_approval_shows_only_the_start_and_says_so(client):
    h = login(client)
    with client.app.state.ctx.factory() as s:
        d = Draft(author_id=1, kind="newsletter", title="Long two", text=LONG, created_by="owner@example.test")
        s.add(d)
        s.flush()
        a = request_approval(s, "draft.approve", "Approve draft: Long two", {"draft_id": d.id, "text_sha256": digest(LONG)}, "medium", "owner@example.test")
        a.status = "rejected"
        s.commit()
        wanted = a.id
    row = next(x for x in client.get("/api/approvals", headers=h).json() if x["id"] == wanted)
    assert len(row["preview"]["text"]) == 1200 and row["preview"]["truncated"] is True


def test_a_draft_changed_in_the_database_after_the_request_cannot_be_approved(client):
    h, approver = login(client), login(client, "approver@example.test")
    ap = pending(client, h)
    with client.app.state.ctx.factory() as s:
        d = s.get(Draft, ap["payload"]["draft_id"])
        d.text += " And an unreviewed extra paragraph that nobody read."
        s.commit()
    r = client.post(f"/api/approvals/{ap['id']}/decide", headers=approver, json={"approve": True})
    assert r.status_code == 409 and "changed after it was sent" in r.json()["error"]["message"]
    with client.app.state.ctx.factory() as s:
        assert s.get(Approval, ap["id"]).status == "pending" and s.get(Draft, ap["payload"]["draft_id"]).status == "pending_approval"


def test_the_fingerprint_the_approver_was_shown_must_still_match(client):
    h, approver = login(client), login(client, "approver@example.test")
    ap = pending(client, h)
    shown = ap["preview"]["text_sha256"]
    assert client.post(f"/api/approvals/{ap['id']}/decide", headers=approver, json={"approve": True, "text_sha256": digest("some other words")}).status_code == 409
    assert client.post(f"/api/approvals/{ap['id']}/decide", headers=approver, json={"approve": True, "text_sha256": shown}).status_code == 200


def test_a_rejection_does_not_need_the_text_to_match(client):
    h, approver = login(client), login(client, "approver@example.test")
    ap = pending(client, h)
    with client.app.state.ctx.factory() as s:
        s.get(Draft, ap["payload"]["draft_id"]).text += " Changed."
        s.commit()
    assert client.post(f"/api/approvals/{ap['id']}/decide", headers=approver, json={"approve": False}).status_code == 200


def test_the_request_stores_the_fingerprint_of_the_exact_text(client):
    h = login(client)
    d = client.get("/api/drafts?status=draft", headers=h).json()[0]
    clean = "Invoices go out on the day the work ends. Short email, due date first, a thank you at the end."
    client.put(f"/api/drafts/{d['id']}", headers=h, json={"text": clean})
    assert client.post(f"/api/drafts/{d['id']}/request-approval", headers=h).status_code == 200
    ap = next(a for a in client.get("/api/approvals", headers=h).json() if a["payload"].get("draft_id") == d["id"] and a["status"] == "pending")
    assert ap["payload"]["text_sha256"] == digest(clean)


def test_export_schedule_and_send_refuse_text_that_changed_after_approval(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    with ctx.factory() as s:
        s.get(Draft, did).text += " A last minute line added after the approval."
        s.commit()
    for call in (lambda: c.post(f"/api/drafts/{did}/export", headers=h, json={}), lambda: c.post(f"/api/drafts/{did}/schedule", headers=h, json={"platform": "linkedin", "run_on": "2026-12-05"}),
                 lambda: c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False})):
        r = call()
        assert r.status_code == 409 and "approve" in r.json()["error"]["message"].lower()
    assert rec.posts == []
    assert not list(tmp_path.glob("exports/*"))  # nothing was written to the export folder either


def test_an_approval_with_no_fingerprint_is_refused_and_can_be_asked_for_again(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    with ctx.factory() as s:  # an approval from before approvals were tied to the text
        a = s.get(Approval, s.get(Draft, did).approval_id)
        a.payload = {"draft_id": did}
        s.commit()
    r = c.post(f"/api/drafts/{did}/export", headers=h, json={})
    assert r.status_code == 409 and "approve the draft again" in r.json()["error"]["message"]
    assert c.post(f"/api/drafts/{did}/request-approval", headers=h).status_code == 200  # an approved draft whose approval does not match may be asked for again
    with ctx.factory() as s:
        assert s.get(Draft, did).status == "pending_approval"
    new = pending(c, h)
    assert new["payload"]["text_sha256"]
    assert c.post(f"/api/approvals/{new['id']}/decide", headers=login(c, "approver@example.test"), json={"approve": True}).status_code == 200
    assert c.post(f"/api/drafts/{did}/export", headers=h, json={}).status_code == 200


def test_an_approved_draft_with_a_matching_approval_cannot_be_asked_for_again(client):
    h, did = approve_the_waiting_draft(client)
    assert client.post(f"/api/drafts/{did}/request-approval", headers=h).status_code == 409


def test_editing_an_approved_draft_still_voids_the_approval(client):
    h, did = approve_the_waiting_draft(client)
    r = client.put(f"/api/drafts/{did}", headers=h, json={"text": "Invoices go out on the day the work ends. Short email, due date first."})
    assert r.json()["status"] == "draft"
    assert client.post(f"/api/drafts/{did}/export", headers=h, json={}).status_code == 409


def test_the_draft_row_is_locked_while_it_is_edited_decided_or_sent(client, monkeypatch):
    from sqlalchemy.orm import Session

    seen = []
    real = Session.execute

    def spy(self, statement, *a, **k):
        if getattr(statement, "_for_update_arg", None) is not None:
            seen.append(statement)
        return real(self, statement, *a, **k)

    monkeypatch.setattr(Session, "execute", spy)
    h, approver = login(client), login(client, "approver@example.test")
    ap = pending(client, h)
    client.post(f"/api/approvals/{ap['id']}/decide", headers=approver, json={"approve": True})
    assert len(seen) >= 1  # the decision held the draft row
    n = len(seen)
    client.put(f"/api/drafts/{ap['payload']['draft_id']}", headers=h, json={"text": "A new version of the text, long enough to be a draft."})
    assert len(seen) > n  # so did the edit


def test_an_edit_is_audited_by_fingerprint_never_by_the_text(client):
    h = login(client)
    d = client.get("/api/drafts?status=draft", headers=h).json()[0]
    client.put(f"/api/drafts/{d['id']}", headers=h, json={"text": "Short text that has changed."})
    log = client.get("/api/audit?limit=5", headers=h).json()
    edited = next(e for e in log if e["action"] == "draft.edited")
    assert edited["detail"]["sha256"] == digest("Short text that has changed.") and "Short text" not in str(edited["detail"])
