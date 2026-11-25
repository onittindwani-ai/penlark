"""Round 2: the claims check, the profile build speed, and the cost of /api/match."""

from __future__ import annotations

import time

import pytest

from penlark import fingerprint, house_rules
from penlark.textstats import measure

NOTE = {1: "In 2025 we looked at 15 percent of invoices and the total was 1500 dollars."}


@pytest.mark.parametrize("claim", ["We grew revenue by 5 percent.", "I saved 50 hours last month.", "We sent 150 reminders.", "We cut it by 1 percent."])
def test_a_figure_that_is_only_part_of_a_longer_number_is_not_sourced(claim):
    out = house_rules.check_claims(claim, NOTE)
    assert out and not out[0]["supported"], claim


@pytest.mark.parametrize("claim", ["We grew revenue by 15 percent.", "We grew revenue by 15%.", "The total was 1,500 dollars.", "The total was 1500 dollars."])
def test_the_same_figure_written_another_way_is_sourced(claim):
    out = house_rules.check_claims(claim, NOTE)
    assert out and out[0]["supported"] and out[0]["source_note_id"] == 1, claim


def test_a_linked_note_must_hold_the_whole_figure_too():
    out = house_rules.check_claims("We saved 50 hours.", {1: "It took 1500 hours in all."}, {"We saved 50 hours.": 1})
    assert not out[0]["supported"]
    assert house_rules.check_claims("We saved 50 hours.", {1: "It took 50 hours in all."}, {"We saved 50 hours.": 1})[0]["supported"]


def test_a_percent_figure_is_not_the_same_as_a_plain_figure():
    assert not house_rules.check_claims("I saved 10 hours.", {1: "Revenue went up 10 percent."})[0]["supported"]
    assert house_rules.check_claims("Revenue went up 10%.", {1: "Revenue went up 10 percent."})[0]["supported"]


def test_measure_counts_function_words_in_one_pass_and_gives_the_same_numbers():
    text = "Honestly, I think you should just call them. It is what we did, and it worked well enough. Now we do it every week."
    m = measure(text)
    ws = [w.lower() for w in __import__("penlark.textstats", fromlist=["words"]).words(text)]
    assert m.habits["the"] == ws.count("the") / len(ws) and m.habits["we"] == ws.count("we") / len(ws)


def test_a_match_of_the_longest_text_is_cheap():
    from penlark.match import match

    sample = " ".join(f"Sentence number {i}, written plainly, so that you can follow it without trouble." for i in range(400))[:30000]
    stats = fingerprint.build_profile([sample[:6000], sample[6000:12000], sample[12000:18000]])
    t0 = time.process_time()
    match(sample, stats)
    assert time.process_time() - t0 < 0.5


def test_building_a_profile_from_hundreds_of_long_samples_stays_fast(monkeypatch):
    texts = [f"Post {i}. " + " ".join(f"I wrote sentence {j} about invoices, reminders and the way people pay on time." for j in range(6)) + f" Unique ending {i}." for i in range(300)]
    t0 = time.process_time()
    prof = fingerprint.build_profile(texts)
    ex = fingerprint.examples(texts)
    assert time.process_time() - t0 < 4, "300 posts must build in a few seconds, not a minute"
    assert prof["n_samples"] == 300 and ex["sentence_length"]


# ---- the link guard, the numbers a person can type, and the secrets in the settings text ----


@pytest.mark.parametrize("url", ["https://evil.com\\.example.com/x", "https://evil.com%5c.example.com/x", "https://evil.com\\@www.example.com/", "https://ex ample.com/", "https://user@www.example.com/"])
def test_the_link_guard_refuses_addresses_that_a_browser_reads_differently(url):
    from penlark import attribution

    assert attribution.host_allowed(url, ["*.example.com", "example.com"]) is False
    assert attribution.host_matches("evil.com\\.example.com", ["*.example.com"]) is False


def test_the_link_guard_still_allows_a_real_host_and_a_real_subdomain():
    from penlark import attribution

    assert attribution.host_allowed("https://www.example.com/a?b=1", ["*.example.com"]) is True
    assert attribution.host_allowed("https://example.com/a", ["example.com"]) is True
    assert attribution.host_allowed("https://example.com/a", ["*.example.com"]) is False


def test_a_draft_link_with_a_backslash_is_not_treated_as_the_owners():
    from penlark import service
    from penlark.config import Settings

    st = Settings(redirect_allow_hosts="*.example.com", public_base_url="https://www.example.com", _env_file=None)
    assert service.foreign_links("Read it at https://www.example.com/post please.", st) == []
    assert service.foreign_links("Read it at https://evil.com\\.example.com/post please.", st) != []


@pytest.mark.parametrize("bad", ["inf", "-inf", "nan", "1e999", "99999999999999999999999"])
def test_a_post_numbers_file_with_an_impossible_count_is_reported_not_a_crash(bad):
    from penlark import learning

    rows, problems = learning.parse_csv(f"post_ref,impressions,likes,text\nr1,{bad},1,A post that is long enough to count\nr2,100,5,Another post that is long enough\n")
    assert [r["impressions"] for r in rows] == [100] and len(problems) == 1


def test_the_import_route_answers_with_a_problem_list_for_an_infinite_count(client):
    from conftest import login

    h = login(client)
    r = client.post("/api/performance/import", headers=h, json={"csv": "post_ref,impressions,likes,text\nr1,1e999,1,A post that is long enough to count\n", "preview": True})
    assert r.status_code == 200 and r.json()["rows"] == 0 and r.json()["problems"]


@pytest.mark.parametrize("path,method,body", [
    ("/api/match", "post", {"author_id": 10**30, "text": "x"}),
    ("/api/match", "post", {"author_id": 1, "text": "x", "source_note_ids": [10**30]}),
    ("/api/match", "post", {"author_id": 1, "text": "x", "claim_links": {"a": 10**30}}),
    ("/api/samples", "post", {"author_id": 2**31, "text": "x" * 30}),
    ("/api/profile/build", "post", {"author_id": 0}),
    ("/api/drafts/99999999999999999999", "get", None),
    ("/api/drafts/99999999999999999999/variants/1/use", "post", None),
    ("/api/samples?author_id=99999999999999999999", "get", None),
    ("/api/profile?author_id=-1", "get", None),
    ("/api/approvals/99999999999999999999/decide", "post", {"approve": True}),
])
def test_an_id_too_big_for_the_database_is_a_plain_422_never_a_500(client, path, method, body):
    from conftest import login

    h = login(client)
    r = getattr(client, method)(path, headers=h, **({"json": body} if body is not None else {}))
    assert r.status_code == 422, (path, r.status_code, r.text[:200])


def test_too_many_attached_notes_are_refused(client):
    from conftest import login

    h = login(client)
    assert client.post("/api/match", headers=h, json={"author_id": 1, "text": "x", "source_note_ids": list(range(1, 600))}).status_code == 422


def test_vendor_keys_and_hashes_are_not_in_the_text_of_the_settings():
    from penlark.config import Settings

    st = Settings(postiz_api_key="pz-secret-value-1", buffer_token="bf-secret-value-2", metricool_token="mc-secret-value-3", lead_webhook_secret="hook-secret-value-4", anthropic_api_key="an-secret-value-5",
                  owner_password_hash="hash-secret-value-6", approver_password_hash="hash-secret-value-7", viewer_password_hash="hash-secret-value-8", session_secret="session-secret-value-9-long-enough", _env_file=None)
    text = repr(st) + str(st)
    for needle in ("pz-secret", "bf-secret", "mc-secret", "hook-secret", "an-secret", "hash-secret", "session-secret"):
        assert needle not in text, needle


def test_a_too_short_session_secret_is_reported_without_printing_it(tmp_path):
    import pytest

    from penlark.config import load_settings
    from sendora_core.settings import ConfigError

    env = tmp_path / "bad.env"
    env.write_text("SESSION_SECRET=short-secret-1\n")
    with pytest.raises(ConfigError) as err:
        load_settings(str(env))
    assert "short-secret-1" not in str(err.value) and "SESSION_SECRET" in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__


def test_the_declared_dependencies_are_the_ones_the_code_uses():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    toml = (root / "apps/api/pyproject.toml").read_text()
    src = "\n".join(p.read_text() for p in (root / "apps/api/src/penlark").rglob("*.py"))
    assert "reportlab" not in toml and "pillow" not in toml.lower() and not re.search(r'^\s*"cryptography', toml, re.M)
    assert "pypdf[crypto]" in toml and "reportlab" not in src and "PIL" not in src
    pins = (root / "constraints.txt").read_text()
    assert "reportlab" not in pins and "pillow" not in pins and "cryptography==" in pins  # pypdf's crypto extra needs it


def test_a_pdf_with_the_empty_password_still_reads():
    """AES encryption needs the cryptography package: this is why it stays, as pypdf's crypto extra."""
    import io

    from pypdf import PdfReader, PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.encrypt("", algorithm="AES-256")
    buf = io.BytesIO()
    w.write(buf)
    assert len(PdfReader(io.BytesIO(buf.getvalue())).pages) == 1
