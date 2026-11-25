"""Shared set up for the hardening tests: a real (not demo) install, and a live scheduler that records what reaches it."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from penlark.adapters.schedulers import Postiz
from penlark.api.app import create_app
from penlark.config import Settings
from penlark.context import Ctx
from sendora_core.auth import hash_password
from sendora_core.db import Base, make_engine, make_session_factory
from sendora_core.settings import Mode

ROOT = Path(__file__).resolve().parents[3]
DATA = str(ROOT / "data")
REAL_SECRET = "test-only-Rt7Kq2Vw9Xm4Zc8Lb3Nf6Hy1Js5Dp0Ga2Ue7Tq4Wi9"
PASSWORD = "a-long-test-password-1"
OWNER = "sam@rivera.example.test"
APPROVER = "robin@rivera.example.test"
VIEWER = "casey@rivera.example.test"
_HASH = hash_password(PASSWORD)  # hashing is slow on purpose: do it once


def real_settings(tmp_path, **kw) -> Settings:
    """A real install: demo off, a long secret, an owner, an approver and a viewer who all sign in with the same test password."""
    base = dict(database_url=f"sqlite:///{tmp_path / 'r.sqlite3'}", demo_mode=False, session_secret=REAL_SECRET, owner_email=OWNER, owner_password_hash=_HASH,
                approver_email=APPROVER, approver_password_hash=_HASH, viewer_email=VIEWER, viewer_password_hash=_HASH, export_dir=str(tmp_path / "exports"),
                lead_webhook_secret="test-only-lead-secret", redirect_allow_hosts="example.org", seed_dir=DATA, _env_file=None)
    base.update(kw)
    return Settings(**base)


def real_client(tmp_path, **kw) -> TestClient:
    return TestClient(create_app(real_settings(tmp_path, **kw)), base_url="http://api.test")


def login(client: TestClient, email: str = OWNER, password: str = PASSWORD) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"x-session": r.json()["token"], "x-penlark": "1"}


class RecordingPostiz:
    """A Postiz stand in served by httpx's mock transport: it records every post that reaches it and can be told to fail."""

    def __init__(self, status: int = 200):
        self.status, self.posts = status, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            self.posts.append(request.content)
            if self.status != 200:
                return httpx.Response(self.status, json={"error": "boom"})
            return httpx.Response(200, json=[{"postId": f"pz-{len(self.posts)}"}])
        return httpx.Response(200, json=[])


def live_app(tmp_path, status: int = 200, **kw):
    """A demo database in live mode with a Postiz adapter that records what it is asked to send. Returns (client, recorder, ctx)."""
    st = Settings(database_url=f"sqlite:///{tmp_path / 'live.sqlite3'}", session_secret="test-secret-test-secret", seed_dir=DATA, mode=Mode.LIVE, postiz_api_key="pz-test-only-key",
                  lead_webhook_secret="s", export_dir=str(tmp_path / "exports"), _env_file=None, **kw)
    rec = RecordingPostiz(status)
    eng = make_engine(st.database_url)
    Base.metadata.create_all(eng)
    adapter = Postiz(st, httpx.Client(base_url="http://postiz.test/public/v1", transport=httpx.MockTransport(rec.handler)))
    ctx = Ctx(st, make_session_factory(eng), scheduler=adapter)
    return TestClient(create_app(st, ctx)), rec, ctx


def approve_the_waiting_draft(c: TestClient) -> tuple[dict, int]:
    """The demo has one draft waiting for a second person. The approver approves it. Returns the owner's headers and the draft id."""
    from conftest import login as demo_login

    h = demo_login(c)
    pend = next(a for a in c.get("/api/approvals", headers=h).json() if a["status"] == "pending")
    r = c.post(f"/api/approvals/{pend['id']}/decide", headers=demo_login(c, "approver@example.test"), json={"approve": True})
    assert r.status_code == 200, r.text
    return h, pend["payload"]["draft_id"]
