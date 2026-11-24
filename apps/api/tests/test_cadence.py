from datetime import date

import pytest

from penlark import cadence
from penlark.config import Settings
from conftest import login


def test_default_rhythm_is_two_posts_a_week_on_linkedin_and_x():
    assert Settings(_env_file=None).cadence == "linkedin:2,x:2"
    assert cadence.parse(Settings(_env_file=None).cadence) == {"linkedin": 2, "x": 2}


@pytest.mark.parametrize("spec,want", [("", {}), (" linkedin : 3 , X:0 ", {"linkedin": 3, "x": 0}), ("newsletter:1", {"newsletter": 1})])
def test_parse_accepts_plain_specs(spec, want):
    assert cadence.parse(spec) == want


@pytest.mark.parametrize("spec", ["linkedin", "linkedin:two", "tiktok:2", "x:2,x:3", "x:-1", "x:22", "linkedin:2:3"])
def test_parse_refuses_wrong_specs_with_a_plain_message(spec):
    with pytest.raises(ValueError, match="CADENCE"):
        cadence.parse(spec)


def test_weeks_run_monday_to_sunday():
    assert cadence.week_start(date(2026, 11, 22)) == date(2026, 11, 16)  # a Sunday
    assert cadence.week_start(date(2026, 11, 23)) == date(2026, 11, 23)  # a Monday


def test_status_counts_planned_items_per_week_and_platform_and_skips_failed():
    rows = [("linkedin", "2026-11-23", "planned"), ("linkedin", "2026-11-29", "exported"), ("x", "2026-11-24", "planned"), ("x", "2026-11-25", "failed"),
            ("linkedin", "2026-12-01", "planned"), ("instagram", "2026-11-24", "planned"), ("x", "bad-date", "planned")]
    out = cadence.status(rows, date(2026, 11, 25), {"linkedin": 2, "x": 2}, weeks=2)
    w0, w1 = out
    assert w0["week_start"] == "2026-11-23" and w0["week_end"] == "2026-11-29"
    assert w0["platforms"]["linkedin"] == {"planned": 2, "target": 2, "gap": 0}
    assert w0["platforms"]["x"] == {"planned": 1, "target": 2, "gap": 1}
    assert w0["on_track"] is False and "instagram" not in w0["platforms"]
    assert w1["week_start"] == "2026-11-30" and w1["platforms"]["linkedin"]["planned"] == 1


def test_status_with_no_target_is_always_on_track_and_weeks_are_capped():
    out = cadence.status([], date(2026, 11, 25), {}, weeks=99)
    assert len(out) == 12 and all(w["on_track"] and w["platforms"] == {} for w in out)


def test_a_wrong_cadence_is_a_config_problem():
    assert any("CADENCE" in p for p in Settings(cadence="tiktok:2", _env_file=None).problems())
    assert not any("CADENCE" in p for p in Settings(_env_file=None).problems())


def test_cadence_endpoint_follows_the_calendar(client):
    h = login(client)
    r = client.get("/api/cadence?weeks=3", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["targets"] == {"linkedin": 2, "x": 2} and len(body["weeks"]) == 3
    approved = next((d for d in client.get("/api/drafts", headers=h).json() if d["status"] == "approved"), None)
    if approved is None:
        ap = next(a for a in client.get("/api/approvals", headers=h).json() if a["status"] == "pending")
        assert client.post(f"/api/approvals/{ap['id']}/decide", headers=login(client, "approver@example.test"), json={"approve": True}).status_code == 200
        approved = next(d for d in client.get("/api/drafts", headers=h).json() if d["status"] == "approved")
    day = body["weeks"][0]["week_start"]
    assert client.post(f"/api/drafts/{approved['id']}/schedule", headers=h, json={"platform": "x", "run_on": day}).status_code == 200
    again = client.get("/api/cadence", headers=h).json()
    assert again["weeks"][0]["platforms"]["x"]["planned"] == 1 and again["weeks"][0]["platforms"]["x"]["gap"] == 1
    assert client.get("/api/cadence?weeks=0", headers=h).status_code == 422
