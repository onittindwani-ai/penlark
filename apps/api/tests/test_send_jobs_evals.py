import json
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import DATA, ROOT, login
from mock.scheduler_mocks import PostizMock
from penlark import jobs
from penlark.adapters.schedulers import Postiz
from penlark.api.app import create_app
from penlark.config import Settings
from penlark.context import Ctx
from sendora_core.db import Base, make_engine, make_session_factory
from sendora_core.settings import Mode


def live_client(tmp_path, mode):
    st = Settings(database_url=f"sqlite:///{tmp_path/'s.sqlite3'}", session_secret="test-secret-test-secret", seed_dir=DATA, mode=mode, postiz_api_key="pz-mock-key", lead_webhook_secret="s", _env_file=None)
    m = PostizMock()
    eng = make_engine(st.database_url)
    Base.metadata.create_all(eng)
    ctx = Ctx(st, make_session_factory(eng), scheduler=Postiz(st, TestClient(m.app, base_url="http://testserver/public/v1")))
    return TestClient(create_app(st, ctx)), m


def approve_first(c):
    h = login(c)
    pend = next(a for a in c.get("/api/approvals", headers=h).json() if a["status"] == "pending")
    c.post(f"/api/approvals/{pend['id']}/decide", headers=login(c, "approver@example.test"), json={"approve": True})
    return h, pend["payload"]["draft_id"]


def test_send_reaches_the_scheduler_only_live_approved_and_confirmed(tmp_path):
    c, m = live_client(tmp_path, Mode.LIVE)
    h = login(c)
    drafts = c.get("/api/drafts?status=draft", headers=h).json()
    assert c.post(f"/api/drafts/{drafts[0]['id']}/send", headers=h, json={"channel_id": "ch-1", "confirm": True}).status_code == 409  # not approved
    h, did = approve_first(c)
    assert c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": False}).status_code == 409
    assert m.posts == []
    ok = c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False})
    assert ok.status_code == 200 and len(m.posts) == 1
    assert c.get(f"/api/drafts/{did}", headers=h).json()["status"] == "published"
    c.post("/api/settings", headers=h, json={"kill_switch": True})
    did2 = c.get("/api/drafts?status=draft", headers=h).json()[0]["id"]
    assert c.post(f"/api/drafts/{did2}/send", headers=h, json={"channel_id": "ch-1", "confirm": True}).status_code == 409
    assert len(m.posts) == 1


def test_draft_mode_sends_nothing(tmp_path):
    c, m = live_client(tmp_path, Mode.DRAFT)
    h, did = approve_first(c)
    r = c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True})
    assert r.status_code == 409 and "draft" in r.json()["error"]["message"].lower() and m.posts == []


def test_jobs_learn_and_schedule(world):
    with world.factory() as s:
        assert jobs.job_learn(s, world)["patterns"] >= 1
        assert jobs.job_ideas(s, world)["ideas"] >= 2
        assert jobs.schedule_due(s, world) == 1
        s.commit()
    assert set(jobs.make_handlers(world)) == {"learn"}


def test_first_run_evaluations_are_saved_untouched_and_honest():
    v = json.loads((ROOT / "data/eval/voice_first_run.json").read_text())
    f = json.loads((ROOT / "data/eval/flags_first_run.json").read_text())
    assert v["author_texts"] == 24 and v["texts"] == 40
    assert f["drafts"] == 26
    # a paraphrase that is on no list gets through: said plainly in the docs
    from penlark import house_rules

    assert house_rules.check_style("Turbocharge the potential of your cash flow.", house_rules.default_rules()) == []


def test_idea_evidence_is_always_a_real_quote(ro):
    from sqlalchemy import select
    from penlark.models import Idea, Note

    with ro.factory() as s:
        notes = {n.id: n.text for n in s.scalars(select(Note))}
        n = 0
        for i in s.scalars(select(Idea)):
            for e in i.evidence:
                assert e["quote"] in notes[e["note_id"]] and notes[e["note_id"]][e["start"]:e["start"] + len(e["quote"])] == e["quote"]
                n += 1
        assert n >= 6


def test_stress_posts_and_clock(client):
    h = login(client)
    assert client.post("/api/demo/stress-posts", headers=h, json={"n": 300}).json()["added"] == 300
    assert len(client.get("/api/performance?limit=20000", headers=h).json()) == 360
    t0 = client.get("/api/demo/state", headers=h).json()["now"]
    t1 = client.post("/api/demo/advance", headers=h, json={"hours": 24}).json()["now"]
    assert t1 > t0 and client.post("/api/demo/tick", headers=h).json()["learn"]["patterns"] >= 0
