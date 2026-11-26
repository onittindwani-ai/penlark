"""Round 2: what the user is told matches what was saved, and the audit chain survives concurrent writers on SQLite."""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient
from hardening_helpers import OWNER, login, real_settings
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError

from penlark.api.app import create_app
from penlark.models import Author


def test_a_failed_save_is_reported_to_the_user_and_nothing_is_kept(tmp_path):
    app = create_app(real_settings(tmp_path))
    c = TestClient(app, base_url="http://api.test", raise_server_exceptions=False)
    h = login(c, OWNER)
    factory = app.state.ctx.write_factory or app.state.ctx.factory
    arm = {"on": False}

    def fail(_session):
        if arm["on"]:
            raise OperationalError("COMMIT", {}, Exception("database is locked"))

    event.listen(factory, "before_commit", fail)
    arm["on"] = True
    r = c.post("/api/authors", headers=h, json={"name": "Sam Rivera"})
    arm["on"] = False
    assert r.status_code >= 500, "the person must not be told the change was saved when the save failed"
    with factory() as s:
        assert s.scalars(select(Author)).all() == []
    assert c.post("/api/authors", headers=h, json={"name": "Sam Rivera"}).status_code == 200


def test_every_route_closes_its_save_before_the_answer_goes_out():
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "penlark" / "api"
    bare = [f"{p.name}: {m}" for p in src.glob("*.py") for m in re.findall(r"Depends\(db\)", p.read_text())]
    assert bare == [], "use the DB dependency (scope function), so the commit happens before the response is sent"


def _write_concurrently(client, headers, rounds: int, writers: int = 4) -> list[int]:
    codes: list[int] = []
    lock = threading.Lock()
    for r in range(rounds):
        barrier = threading.Barrier(writers)

        def go(i: int, r: int = r):
            barrier.wait()
            # saving a setting to the value it already has changes no row, so the audit entry is the first write of the request: the case that used to fork the chain
            res = client.post("/api/settings", headers=headers, json={"force_draft": False})
            with lock:
                codes.append(res.status_code)

        threads = [threading.Thread(target=go, args=(i,)) for i in range(writers)]
        [t.start() for t in threads]
        [t.join() for t in threads]
    return codes


def test_four_writers_at_once_never_fork_the_audit_chain_on_sqlite(tmp_path):
    from sendora_core.audit import verify_audit_chain

    app = create_app(real_settings(tmp_path))
    c = TestClient(app, base_url="http://api.test")
    h = login(c, OWNER)
    assert c.post("/api/settings", headers=h, json={"force_draft": False}).status_code == 200  # the row exists from now on
    codes = _write_concurrently(c, h, rounds=8)
    assert set(codes) == {200}, codes
    with app.state.ctx.factory() as s:
        assert verify_audit_chain(s) == (True, None)


def test_a_read_is_not_held_up_by_a_writer_that_has_the_lock(tmp_path):
    import time

    app = create_app(real_settings(tmp_path))
    c = TestClient(app, base_url="http://api.test")
    h = login(c, OWNER)
    with app.state.ctx.write_factory() as holder:
        holder.execute(select(Author))  # BEGIN IMMEDIATE: this session now holds the write lock
        t0 = time.perf_counter()
        assert c.get("/api/authors", headers=h).status_code == 200
        assert time.perf_counter() - t0 < 2


# ---- a send whose outcome is unclear ----

import httpx  # noqa: E402
from hardening_helpers import approve_the_waiting_draft, live_app  # noqa: E402

from penlark.models import Draft, Schedule  # noqa: E402


def _send(c, h, did, **kw):
    return c.post(f"/api/drafts/{did}/send", headers=h, json={"channel_id": "ch-1", "confirm": True, "as_draft": False, **kw})


def _status(ctx, did):
    with ctx.factory() as s:
        return s.get(Draft, did).status


def test_a_timeout_leaves_the_draft_held_and_a_second_send_is_refused(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)

    def boom(request):
        rec.posts.append(request.content)
        raise httpx.ReadTimeout("the answer never came", request=request)

    ctx.scheduler.client = httpx.Client(base_url="http://postiz.test/public/v1", transport=httpx.MockTransport(boom))
    r = _send(c, h, did)
    assert r.status_code == 502 and "may or may not" in r.json()["error"]["message"]
    assert _status(ctx, did) == "send_unknown"
    again = _send(c, h, did)
    assert again.status_code == 409 and len(rec.posts) == 1, "a second click must not make a second post"
    assert c.put(f"/api/drafts/{did}", headers=h, json={"text": "New words while nobody knows if the first went out."}).status_code == 409
    assert c.post(f"/api/drafts/{did}/export", headers=h, json={}).status_code == 409
    assert c.post(f"/api/drafts/{did}/request-approval", headers=h).status_code == 409
    assert c.post(f"/api/drafts/{did}/schedule", headers=h, json={"run_on": "2026-12-01"}).status_code == 409
    row = next(x for x in c.get("/api/schedule", headers=h).json() if x["draft_id"] == did)
    assert row["status"] == "unclear" and c.delete(f"/api/schedule/{row['id']}", headers=h).status_code == 409


def test_an_unclear_send_is_never_released_by_the_half_hour_timer(tmp_path):
    from datetime import timedelta

    from penlark import clock

    c, rec, ctx = live_app(tmp_path, status=503)
    h, did = approve_the_waiting_draft(c)
    assert _send(c, h, did).status_code == 502
    with ctx.factory() as s:
        s.get(Draft, did).updated_at = clock.DEMO_START - timedelta(hours=5)
        s.commit()
    assert c.post(f"/api/drafts/{did}/export", headers=h, json={}).status_code == 409
    assert _status(ctx, did) == "send_unknown"


def test_a_person_resolves_an_unclear_send_posted_or_not_posted(tmp_path):
    c, rec, ctx = live_app(tmp_path, status=500)
    h, did = approve_the_waiting_draft(c)
    assert _send(c, h, did).status_code == 502
    posted = c.post(f"/api/drafts/{did}/send-outcome", headers=h, json={"posted": True, "external_id": "pz-77"})
    assert posted.status_code == 200 and posted.json()["status"] == "scheduled"
    row = next(x for x in c.get("/api/schedule", headers=h).json() if x["draft_id"] == did)
    assert row["status"] == "sent"
    assert _send(c, h, did).status_code == 409 and len(rec.posts) == 1  # now it is on record as sent: never a second post
    assert c.post(f"/api/drafts/{did}/send-outcome", headers=h, json={"posted": True}).status_code == 409  # nothing is waiting for an answer any more

    (tmp_path / "second").mkdir()
    c2, rec2, ctx2 = live_app(tmp_path / "second", status=500)
    h2, did2 = approve_the_waiting_draft(c2)
    assert _send(c2, h2, did2).status_code == 502
    not_posted = c2.post(f"/api/drafts/{did2}/send-outcome", headers=h2, json={"posted": False})
    assert not_posted.status_code == 200 and not_posted.json()["status"] == "approved"
    assert not [x for x in c2.get("/api/schedule", headers=h2).json() if x["draft_id"] == did2]
    actions = [e["action"] for e in c2.get("/api/audit?limit=10", headers=h2).json()]
    assert "draft.send_not_posted" in actions and "draft.send_unclear" in actions


def test_only_a_person_who_can_write_may_resolve_it(tmp_path):
    c, rec, ctx = live_app(tmp_path, status=500)
    h, did = approve_the_waiting_draft(c)
    assert _send(c, h, did).status_code == 502
    from conftest import login as demo_login

    viewer = demo_login(c, "viewer@example.test")
    assert c.post(f"/api/drafts/{did}/send-outcome", headers=viewer, json={"posted": False}).status_code == 403


def test_an_unreadable_answer_after_a_success_status_is_treated_as_unclear(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)
    ctx.scheduler.client = httpx.Client(base_url="http://postiz.test/public/v1", transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>not json</html>")))
    assert _send(c, h, did).status_code == 502
    assert _status(ctx, did) == "send_unknown"


def test_a_connection_that_never_opened_is_a_clear_not_sent(tmp_path):
    c, rec, ctx = live_app(tmp_path)
    h, did = approve_the_waiting_draft(c)

    def refuse(request):
        raise httpx.ConnectError("no route", request=request)

    ctx.scheduler.client = httpx.Client(base_url="http://postiz.test/public/v1", transport=httpx.MockTransport(refuse))
    assert _send(c, h, did).status_code == 502
    assert _status(ctx, did) == "approved"


# ---- the container is never a public demo by default ----


def test_the_image_and_the_compose_file_set_demo_mode_off_explicitly():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    assert "ENV DEMO_MODE=false" in (root / "apps/api/Dockerfile").read_text()
    compose = (root / "docker-compose.yml").read_text()
    assert compose.count("DEMO_MODE: ${DEMO_MODE:-false}") == 2, "both the api and the worker must default to a real install"


def test_a_container_with_no_variables_refuses_to_start(monkeypatch):
    import pytest

    from penlark.config import Settings
    from sendora_core.settings import ConfigError

    for name in ("SESSION_SECRET", "OWNER_PASSWORD_HASH", "MODE", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEMO_MODE", "false")  # what the image sets
    with pytest.raises(ConfigError, match="SESSION_SECRET"):
        Settings(_env_file=None).check_runtime()


# ---- an old SQLite file is named, not left to fail later ----


def test_a_sqlite_file_from_an_older_version_stops_the_start_with_a_plain_message(tmp_path):
    import sqlite3

    import pytest

    from sendora_core.settings import ConfigError

    db = tmp_path / "old.sqlite3"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE vp_author (id INTEGER PRIMARY KEY, slug VARCHAR(40), name VARCHAR(120))")  # an older shape: no "about" and no "created_at"
    con.commit()
    con.close()
    with pytest.raises(ConfigError, match="older version") as err:
        create_app(real_settings(tmp_path, database_url=f"sqlite:///{db}"))
    assert "vp_author" in str(err.value) and "docs/12-UPDATING.md" in str(err.value)


def test_a_current_sqlite_file_starts_and_has_nothing_missing(tmp_path):
    from penlark.dbsetup import schema_problems

    app = create_app(real_settings(tmp_path))
    assert schema_problems(app.state.ctx.factory().get_bind()) == []


def test_a_slow_upload_does_not_hold_the_write_lock(tmp_path):
    """The session's first query takes the SQLite write lock, so a route must read its whole body before it asks the database anything, and the database work itself runs on a worker thread.
    (Changed in round 3: the work moved out of the async function into `_store_upload`, so the check is now on the order of the two steps and on nothing touching the session in between.)"""
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src" / "penlark" / "api" / "routes_write.py").read_text()
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.AsyncFunctionDef) and n.name == "upload_sample")
    body = ast.get_source_segment(src, fn)
    assert body.index("read_bounded") < body.index("run_in_threadpool(_store_upload")
    import re

    assert not re.search(r"\bs\.(get|scalars|execute|add|flush)\(|service\.sample_digests", body), "no database call on the event loop"
