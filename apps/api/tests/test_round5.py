"""Round 5: defects found by walking every screen as a first time owner. One test per fix."""
import io

from conftest import login

CLEAN = "Late invoices feel awkward. Chasing them should not.\n\nName the invoice. Name the date. Ask when it will be paid. Stop there.\n\nShort email. Plain words. Send it today."
BAD = "[YOUR ANSWER] We grew 900 percent in a week. In today's fast-paced world it is a game changer."


def _seeded(client, tmp_path=None):
    h = login(client)
    assert client.post("/api/demo/reset", headers=h).status_code == 200
    return h


def test_the_seed_draft_waiting_for_a_second_person_is_finished_writing(client):
    h = _seeded(client)
    d = client.get("/api/drafts/1", headers=h).json()
    assert d["status"] == "pending_approval" and "[" not in d["text"]
    ev = client.get("/api/drafts/1", headers=h).json()["evaluation"]
    assert ev["ready"] and not ev["placeholders"]


def test_editing_a_draft_that_waits_withdraws_the_request_and_the_stale_request_cannot_be_approved(client):
    h, a = _seeded(client), login(client, "approver@example.test")
    assert client.put("/api/drafts/1", headers=h, json={"text": BAD}).status_code == 200
    assert client.get("/api/drafts/1", headers=h).json()["status"] == "draft"
    rows = client.get("/api/approvals", headers=h).json()
    assert rows[0]["status"] == "rejected" and rows[0]["decided_by"] == "system"
    r = client.post("/api/approvals/1/decide", headers=a, json={"approve": True})
    assert r.status_code == 409 and "already" in r.json()["error"]["message"].lower()
    assert client.get("/api/drafts/1", headers=h).json()["status"] == "draft"  # nothing was approved


def test_a_variant_swapped_in_while_waiting_withdraws_the_request_too(client):
    h = _seeded(client)
    d = client.get("/api/drafts/1", headers=h).json()
    vid = d["variants"][0]["id"]
    assert client.post(f"/api/drafts/1/variants/{vid}/use", headers=h).status_code == 200
    assert client.get("/api/approvals", headers=h).json()[0]["status"] == "rejected"


def test_approving_checks_the_draft_again_when_a_house_rule_changed_since_the_request(client):
    h, a = _seeded(client), login(client, "approver@example.test")
    assert client.post("/api/rules", headers=h, json={"kind": "phrase", "value": "plain words"}).status_code == 200
    r = client.post("/api/approvals/1/decide", headers=a, json={"approve": True})
    assert r.status_code == 409 and "no longer passes" in r.json()["error"]["message"]
    assert client.get("/api/approvals", headers=h).json()[0]["status"] == "pending"  # the refusal left the request open


def test_the_approvals_list_shows_the_text_that_would_be_approved(client):
    h = _seeded(client)
    p = client.get("/api/approvals", headers=h).json()[0]["preview"]
    assert p["draft_id"] == 1 and p["text"].startswith("Late invoices feel awkward")


def test_a_draft_remembers_which_voice_it_is_written_in(client):
    h = _seeded(client)
    assert client.put("/api/drafts/2", headers=h, json={"text": CLEAN, "author_id": 2}).status_code == 200
    assert client.get("/api/drafts/2", headers=h).json()["author_id"] == 2
    assert client.put("/api/drafts/2", headers=h, json={"text": CLEAN, "author_id": 99}).status_code == 404


def test_changing_the_voice_of_a_waiting_draft_withdraws_the_request(client):
    h = _seeded(client)
    assert client.put("/api/drafts/1", headers=h, json={"text": client.get("/api/drafts/1", headers=h).json()["text"], "author_id": 2}).status_code == 200
    assert client.get("/api/drafts/1", headers=h).json()["status"] == "draft"


def test_a_draft_kind_must_be_one_the_screen_offers(client):
    h = _seeded(client)
    assert client.post("/api/ideas/1/draft", headers=h, json={"author_id": 1, "kind": "zzz"}).status_code == 422


def test_a_note_of_only_spaces_is_refused(client):
    h = _seeded(client)
    r = client.post("/api/notes", headers=h, json={"kind": "call", "who": "", "text": "          "})
    assert r.status_code == 400


def test_the_same_banned_phrase_is_not_added_twice(client):
    h = _seeded(client)
    assert client.post("/api/rules", headers=h, json={"kind": "phrase", "value": "synergy hour"}).status_code == 200
    r = client.post("/api/rules", headers=h, json={"kind": "phrase", "value": "  Synergy Hour "})
    assert r.status_code == 409 and "already" in r.json()["error"]["message"]
    assert client.post("/api/rules", headers=h, json={"kind": "phrase", "value": "game changer"}).status_code == 409  # a built in one counts


def test_the_same_sample_is_not_added_twice_and_a_second_upload_adds_nothing(client):
    h = _seeded(client)
    text = "Plan the week on Sunday. Three goals. Not ten, never ten, not even close to ten goals."
    assert client.post("/api/samples", headers=h, json={"author_id": 1, "text": text}).status_code == 200
    assert client.post("/api/samples", headers=h, json={"author_id": 1, "text": text.upper()}).status_code == 409
    body = ("First sample sentence. " * 12).encode()
    up = client.post("/api/samples/upload?author_id=1", headers={**h, "x-filename": "notes.txt"}, content=body)
    again = client.post("/api/samples/upload?author_id=1", headers={**h, "x-filename": "notes.txt"}, content=body)
    assert up.json()["added"] == 1 and again.json() == {"added": 0, "skipped": 1}


def test_a_sample_for_a_voice_that_does_not_exist_is_a_clear_404(client):
    h = _seeded(client)
    assert client.post("/api/samples", headers=h, json={"author_id": 99, "text": "x" * 40}).status_code == 404
    assert client.post("/api/samples/upload?author_id=99", headers={**h, "x-filename": "a.txt"}, content=b"word " * 40).status_code == 404


def test_pressing_make_the_link_twice_gives_the_same_link(client):
    h = _seeded(client)
    body = {"target": "https://larkspur.example.test/start", "campaign": "twice", "source": "linkedin"}
    one, two = client.post("/api/links", headers=h, json=body).json(), client.post("/api/links", headers=h, json=body).json()
    assert one["code"] == two["code"] and one["existing"] is False and two["existing"] is True and one["short_path"] == f"/r/{one['code']}"
    rows = client.get("/api/links", headers=h).json()
    assert [r["code"] for r in rows].count(one["code"]) == 1 and all(r["short_path"].startswith("/r/") for r in rows) and rows[0]["base_is_default"] is True


def test_exporting_a_planned_draft_keeps_one_calendar_entry_on_the_planned_day_and_platform(client):
    h, a = _seeded(client), login(client, "approver@example.test")
    assert client.post("/api/approvals/1/decide", headers=a, json={"approve": True}).status_code == 200
    assert client.post("/api/drafts/1/schedule", headers=h, json={"platform": "x", "run_on": "2026-12-05"}).status_code == 200
    r = client.post("/api/drafts/1/export", headers=h, json={})
    assert r.status_code == 200 and "-x-" in r.json()["external_id"]
    rows = client.get("/api/schedule", headers=h).json()
    assert len(rows) == 1 and rows[0]["status"] == "exported" and rows[0]["run_on"] == "2026-12-05" and rows[0]["platform"] == "x"


def test_exporting_a_draft_that_was_never_planned_adds_one_entry_for_today(client):
    h, a = _seeded(client), login(client, "approver@example.test")
    assert client.post("/api/approvals/1/decide", headers=a, json={"approve": True}).status_code == 200
    assert client.post("/api/drafts/1/export", headers=h, json={}).status_code == 200
    rows = client.get("/api/schedule", headers=h).json()
    assert len(rows) == 1 and rows[0]["status"] == "exported" and rows[0]["platform"] == "linkedin"
    assert client.post("/api/drafts/1/export", headers=h, json={"platform": "myspace"}).status_code in {409, 422}


def test_the_same_csv_imported_twice_adds_each_post_once(client):
    h = _seeded(client)
    csv = "impressions,likes,comments,shares,text\n1000,40,3,2,An imported post about reminders for late clients.\n900,30,2,1,A second imported post about invoices.\n900,30,2,1,A second imported post about invoices.\n"
    before = client.get("/api/overview", headers=h).json()["posts"]
    prev = client.post("/api/performance/import", headers=h, json={"csv": csv, "preview": True}).json()
    assert prev["rows"] == 2 and prev["duplicates"] == 1  # a repeated line inside the file counts once too
    one = client.post("/api/performance/import", headers=h, json={"csv": csv, "preview": False}).json()
    two = client.post("/api/performance/import", headers=h, json={"csv": csv, "preview": False}).json()
    assert one["rows"] == 2 and two["rows"] == 0 and two["duplicates"] == 3
    assert client.get("/api/overview", headers=h).json()["posts"] == before + 2


def test_an_empty_file_a_stray_word_or_an_unknown_file_type_is_not_added_as_a_sample(client):
    h = _seeded(client)
    up = lambda name, body: client.post("/api/samples/upload?author_id=1", headers={**h, "x-filename": name}, content=body)  # noqa: E731
    before = len(client.get("/api/samples?author_id=1", headers=h).json())
    assert up("empty.txt", b"").status_code == 400
    assert up("tiny.txt", b"hello").status_code == 400
    r = up("program.exe", b"MZ" + b"x" * 100)
    assert r.status_code == 400 and "not supported" in r.json()["error"]["message"]
    assert up("notes", b"A plain file with no extension. It has enough words to count as a sample.").status_code == 200
    assert len(client.get("/api/samples?author_id=1", headers=h).json()) == before + 1
