"""Load the fictional demo world from data/seed. Three fictional authors, notes, 60 posts with numbers, tracked links, experiments."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from penlark import service
from penlark.datadir import data_dir
from penlark.models import Author, Click, Conversion, Draft, Experiment, Link, Note, Performance, Sample, Schedule
from sendora_core.approvals import request_approval

DEMO_DEFAULT_REQUESTER = "owner@example.test"
SEED_WAITING_TEXT = """Late invoices feel awkward. Chasing them should not.

Name the invoice. Name the date. Ask when it will be paid. Stop there.

Short email. Plain words. Send it today."""


def _load(seed: Path, name: str):
    return json.loads((seed / name).read_text())


def load_world(s: Session, ctx) -> dict:
    seed = data_dir(ctx.settings.seed_dir) / "seed"
    now = ctx.now(s)
    authors = {}
    for a in _load(seed, "authors.json"):
        row = Author(slug=a["slug"], name=a["name"], about=a["about"])
        s.add(row)
        s.flush()
        authors[a["slug"]] = row
        for i, t in enumerate(_load(seed, f"samples_{a['slug']}.json"), start=1):
            s.add(Sample(author_id=row.id, title=f"Sample {i}: {t.strip().splitlines()[0][:50]}", kind="text", text=t, source="seed (fictional)"))
    s.flush()
    notes = []
    for n in _load(seed, "notes.json"):
        row = Note(id=int(n["id"][1:]), kind=n["kind"], who=n["who"], text=n["text"], occurred_on=n["date"])
        s.add(row)
        notes.append(row)
    s.flush()
    for p in _load(seed, "posts.json"):
        s.add(Performance(post_ref=p["post_ref"], platform=p["platform"], posted_on=p["posted_on"], text=p["text"], impressions=p["impressions"], likes=p["likes"], comments=p["comments"], shares=p["shares"], clicks=p["clicks"]))
    lk = _load(seed, "links.json")
    for l in lk["links"]:
        s.add(Link(id=l["id"], code=l["code"], target=l["target"] + f"?utm_source={l['source']}&utm_medium={l['medium']}&utm_campaign={l['campaign']}", post_ref=l["post_ref"], source=l["source"], medium=l["medium"], campaign=l["campaign"]))
    s.flush()
    for c in lk["clicks"]:
        s.add(Click(link_id=c["link_id"], visitor=c["visitor"], at=now - timedelta(days=c["day"])))
    for c in lk["conversions"]:
        s.add(Conversion(link_id=c["link_id"], lead_ref=c["lead_ref"], kind=c["kind"], value=c["value"], at=now))
    for e in _load(seed, "experiments.json"):
        s.add(Experiment(name=e["name"], metric=e["metric"], a_label=e["a_label"], b_label=e["b_label"], a_n=e["a_n"], a_hits=e["a_hits"], b_n=e["b_n"], b_hits=e["b_hits"]))
    service.ensure_builtin_rules(s)
    n_ideas = service.load_ideas(s, notes, ctx)
    for a in authors.values():
        pr = service.build_profile(s, a.id, "system", ctx)
        pr.locked, pr.locked_by = True, "demo seed"
    s.flush()
    t = authors["tobias"]
    from sqlalchemy import select
    from penlark.models import Idea

    top = list(s.scalars(select(Idea).order_by(Idea.score.desc()).limit(2)))
    drafts = []
    for i, idea in enumerate(top):
        d = service.create_drafts_from_idea(s, ctx, idea.id, t.id, "post", "owner@example.test")
        drafts.append(d)
    # the draft waiting for a second person is finished writing, with no brackets, so approving it in the demo is a real decision
    drafts[0].text = SEED_WAITING_TEXT
    drafts[0].status = "pending_approval"
    drafts[0].approval_id = request_approval(s, "draft.approve", f"Approve draft: {drafts[0].title}", {"draft_id": drafts[0].id, "text_sha256": service.text_digest(SEED_WAITING_TEXT)}, "medium", DEMO_DEFAULT_REQUESTER).id
    s.flush()
    return {"authors": len(authors), "notes": len(notes), "ideas": n_ideas, "posts": 60, "drafts": len(drafts)}
