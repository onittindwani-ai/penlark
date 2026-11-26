"""Round 2: the idea finder stays small on hostile notes, and the refresh button works through the worker on a real install."""

from __future__ import annotations

import random
import time
import tracemalloc

from hardening_helpers import OWNER, login, real_client
from sqlalchemy import select

from penlark import ideas, jobs
from penlark.models import Idea, Note
from sendora_core.jobs import Worker
from sendora_core.models import Job


def _hostile_notes(n_notes: int = 4, words_per: int = 1200, pool: int = 3500) -> list[dict]:
    """Long notes whose words are shared with only a few other notes, so every word counts as a possible theme (the worst case for the pair table)."""
    rnd = random.Random(1)
    vocab = ["".join(rnd.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(rnd.randint(5, 10))) + "x" for _ in range(pool)]
    out = []
    for i in range(1, n_notes + 1):
        ws = rnd.sample(vocab, words_per)
        out.append({"id": i, "kind": "call", "text": ". ".join(" ".join(ws[j:j + 10]) for j in range(0, words_per, 10)) + "."})
    return out


def test_the_idea_finder_does_not_grow_with_the_square_of_a_long_note():
    notes = _hostile_notes()
    tracemalloc.start()
    t0 = time.perf_counter()
    ideas.find_ideas(notes)
    took = time.perf_counter() - t0
    peak = tracemalloc.get_traced_memory()[1] / 1e6
    tracemalloc.stop()
    assert peak < 60, f"the idea finder held {peak:.0f} MB for four long notes"
    assert took < 6, f"the idea finder took {took:.1f} s for four long notes"


def _letters(k: int) -> str:
    return "".join(chr(97 + int(d)) for d in str(k)) + "qx"


def test_the_idea_finder_keeps_only_the_newest_notes_and_a_bounded_amount_of_text():
    total = ideas.MAX_NOTES + 50
    many = []
    for i in range(1, total + 1):
        a, b = _letters(i % 40), _letters(1000 + i % 40)
        many.append({"id": i, "kind": "note", "text": f"Customers keep asking about {a} and {b} again and again every single week."})
    out = ideas.find_ideas(many)
    seen = {nid for i in out for nid in i.note_ids}
    assert seen and min(seen) > 50, "the oldest notes should have been left out"
    assert len(ideas.limit_notes([{"id": n, "kind": "n", "text": "x" * 20000} for n in range(200)], max_chars=100_000)) == 5
    assert ideas.limit_notes([{"id": 1, "kind": "n", "text": "y" * 30000}])[0]["text"] == "y" * ideas.MAX_NOTE_CHARS


def test_the_same_ideas_come_from_the_seed_notes_as_before():
    import json
    from pathlib import Path

    notes = json.loads((Path(__file__).resolve().parents[3] / "data" / "seed" / "notes.json").read_text())
    rows = [{"id": i + 1, "kind": n["kind"], "text": n["text"]} for i, n in enumerate(notes)]
    out = ideas.find_ideas(rows)
    assert len(out) >= 2 and all(i.evidence for i in out)


def _real_with_notes(tmp_path, count: int = 6):
    import json
    from pathlib import Path

    c = real_client(tmp_path)
    h = login(c, OWNER)
    for n in json.loads((Path(__file__).resolve().parents[3] / "data" / "seed" / "notes.json").read_text())[:count]:
        assert c.post("/api/notes", headers=h, json={"kind": n["kind"], "who": "A customer", "text": n["text"]}).status_code == 200
    return c, h


def test_on_a_real_install_the_button_queues_a_job_and_the_worker_does_the_work(tmp_path):
    c, h = _real_with_notes(tmp_path)
    r = c.post("/api/ideas/refresh", headers=h)
    assert r.status_code == 200 and r.json()["queued"] is True
    first = r.json()["job_id"]
    assert c.post("/api/ideas/refresh", headers=h).json()["job_id"] == first  # pressing it again does not stack up more jobs
    assert c.get("/api/ideas", headers=h).json() == []  # nothing was computed inside the request
    st = c.get("/api/ideas/status", headers=h).json()
    assert st["status"] == "queued" and "worker" not in st["message"].lower()
    ctx = c.app.state.ctx
    assert Worker(ctx.factory, jobs.make_handlers(ctx)).drain() == 1
    st = c.get("/api/ideas/status", headers=h).json()
    assert st["status"] == "done" and st["ideas"] >= 1
    assert len(c.get("/api/ideas", headers=h).json()) == st["ideas"]


def test_a_queued_refresh_that_nobody_picks_up_says_the_worker_is_not_running(tmp_path):
    c, h = _real_with_notes(tmp_path, 2)
    c.post("/api/ideas/refresh", headers=h)
    with c.app.state.ctx.factory() as s:
        job = s.scalars(select(Job).where(Job.kind == "ideas")).one()
        from datetime import timedelta

        job.created_at = job.created_at - timedelta(minutes=5)
        s.commit()
    st = c.get("/api/ideas/status", headers=h).json()
    assert st["status"] == "queued" and "worker" in st["message"].lower() and "make worker" in st["message"]


def test_a_viewer_cannot_start_a_refresh_and_the_demo_still_answers_at_once(tmp_path, client):
    from hardening_helpers import VIEWER

    c, _ = _real_with_notes(tmp_path, 2)
    assert c.post("/api/ideas/refresh", headers=login(c, VIEWER)).status_code == 403
    from conftest import login as demo_login

    h = demo_login(client)
    client.post("/api/notes", headers=h, json={"kind": "email", "who": "x", "text": "I am worried the reminder email sounds rude and pushy to my customers."})
    out = client.post("/api/ideas/refresh", headers=h).json()
    assert "ideas" in out and out.get("queued") is not True  # the demo has no worker, so it answers in the request


def test_the_ideas_job_is_not_on_the_hourly_schedule_and_writes_an_audit_row(world):
    assert "ideas" in jobs.make_handlers(world) and "ideas" not in jobs.INTERVALS
    with world.factory() as s:
        assert jobs.job_ideas(s, world)["ideas"] == 2  # the two themes the demo notes hold
        s.commit()
        from sendora_core.models import AuditEntry

        assert any(e.action == "ideas.refreshed" and e.actor == "system" for e in s.scalars(select(AuditEntry)))
        assert s.scalar(select(Note.id).limit(1)) is not None and s.scalar(select(Idea.id).limit(1)) is not None
