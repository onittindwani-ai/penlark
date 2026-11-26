"""A pattern or a pasted text must never freeze the process. The hostile inputs run in a child process with a hard time limit: a regular expression runs inside one
call that cannot be interrupted, so a regression has to fail this test and not hang the whole run."""

import subprocess
import sys
import textwrap

import pytest

from conftest import ROOT, login
from penlark import house_rules, safe_regex

SRC = str(ROOT / "apps/api/src")


def run_timed(body: str, limit: float = 20.0) -> float:
    """Run `body` (Python that may use `t`, a helper that returns elapsed seconds) in a child process. Returns the seconds the work took, or fails when the child ran over `limit`."""
    # the imports come before the clock starts: loading the libraries takes a second or more on a busy machine and is not what is measured
    code = "import sys, time\nsys.path.insert(0, %r)\nimport penlark.house_rules, penlark.ingest, penlark.service\nstart = time.time()\n%s\nprint(time.time() - start)\n" % (SRC, textwrap.dedent(body))
    try:
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        pytest.fail(f"the work did not finish in {limit} seconds: it freezes the process")
    assert out.returncode == 0, out.stderr[-600:]
    return float(out.stdout.strip().splitlines()[-1])


# ---- the pattern check ----

@pytest.mark.parametrize("pattern", [r"(\w+\s?)*$", r"(a+)+$", r"(.*)*x", r"\w+x", r"a*", r"\w{1,}", r"(?:aa|bb){1,5}", r"(a)\1", r"(?(1)a|b)", r"x{1,301}", r"x{1,300}y{1,300}", r"(?:\w{1,20}\s){1,10}", "a" * 201, "(unclosed"])
def test_dangerous_or_invalid_patterns_are_refused(pattern):
    assert safe_regex.problem(pattern)


@pytest.mark.parametrize("pattern", [r"\bsynerg\w{0,20}\b", r"\bwe are (?:thrilled|excited) to\b", r"foo\w{0,30}", r"(?:ab){1,5}", r"\d{1,3}%", r"\b(?:imagine|picture) a world where\b", r"\w{1,40}\s{1,3}\w{1,40}"])
def test_ordinary_bounded_patterns_are_accepted(pattern):
    assert safe_regex.problem(pattern) is None


def test_every_built_in_pattern_passes_the_check():
    assert [pat for pat, _ in house_rules.DEFAULT_PATTERNS if safe_regex.problem(pat)] == []


def test_adding_a_dangerous_rule_is_refused_with_a_plain_reason_and_a_good_one_is_saved(client):
    h = login(client)
    bad = client.post("/api/rules", headers=h, json={"kind": "pattern", "value": r"(\w+\s?)*$", "note": "x"})
    assert bad.status_code == 400 and "upper limit" in bad.json()["error"]["message"]
    assert client.post("/api/rules", headers=h, json={"kind": "pattern", "value": r"(unclosed", "note": "x"}).status_code == 400
    assert client.post("/api/rules", headers=h, json={"kind": "pattern", "value": r"\bsynerg\w{0,20}\b", "note": "A word we never use."}).status_code == 200
    rules = client.get("/api/rules", headers=h).json()["rules"]
    assert not any(r["value"] == r"(\w+\s?)*$" for r in rules)


def test_a_dangerous_rule_that_is_already_stored_is_shown_and_never_run(client):
    from penlark.models import HouseRule

    with client.app.state.ctx.factory() as s:
        s.add(HouseRule(kind="pattern", value=r"(\w+\s?)*$", note="old rule", builtin=False))
        s.commit()
    h = login(client)
    r = client.post("/api/match", headers=h, json={"author_id": 1, "text": ("a" * 60 + "! ") * 400})  # 24,000 characters: the old pattern would never finish
    flags = [f for f in r.json()["rules"]["style"] if f["kind"] == "unsafe_rule"]
    assert flags and "Edit or delete it" in flags[0]["message"] and r.json()["ready"] is False


def test_the_unsafe_pattern_is_skipped_in_a_child_process_with_a_time_limit():
    took = run_timed(r"""
        from penlark import house_rules
        rules = house_rules.Rules([], [(r"(\w+\s?)*$", "old rule")])
        flags = house_rules.check_style("a" * 60 + "!", rules)
        assert [f["kind"] for f in flags] == ["unsafe_rule"]
    """)
    assert took < 10


def test_one_pattern_cannot_raise_more_than_the_cap_of_flags():
    rules = house_rules.Rules([], [(r"\bx{1,2}\b", "x")])
    flags = house_rules.check_style("x " * 5000, rules)
    assert len([f for f in flags if f["kind"] == "banned_pattern"]) == safe_regex.MAX_MATCHES


# ---- pasted and uploaded text ----

HOSTILE = {
    "markdown_open_brackets": "from penlark import ingest\ningest.from_markdown('[' * 200000)",
    "markdown_open_images": "from penlark import ingest\ningest.from_markdown('![' * 100000)",
    "markdown_open_links": "from penlark import ingest\ningest.from_markdown('[a](' * 50000)",
    "transcript_open_tags": "from penlark import ingest\ningest.from_transcript('<' * 200000)",
    "x_archive_equals": "from penlark import ingest\ntry:\n    ingest.from_x_archive('=[' * 100000)\nexcept ingest.IngestError:\n    pass",
    "x_archive_deep_nesting": "from penlark import ingest\ntry:\n    ingest.from_x_archive('[' * 200000 + ']' * 200000)\nexcept ingest.IngestError:\n    pass",
    "placeholders_one_long_run": "from penlark import service\nservice._brackets('[' + 'A' * 30000)",
    "placeholders_many_starts": "from penlark import service\nservice._brackets('[AB' * 10000)",
    "all_the_house_checks": "from penlark import house_rules\nhouse_rules.check_all('a ' * 15000, house_rules.default_rules(), {}, {})",
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_hostile_text_is_handled_in_seconds(name):
    assert run_timed(HOSTILE[name], limit=30) < 10


def test_a_pasted_sample_of_open_brackets_through_the_api_is_quick(client):
    import time

    h = login(client)
    start = time.time()
    r = client.post("/api/samples", headers=h, json={"author_id": 1, "text": "[" * 190000, "kind": "markdown"})
    assert r.status_code in (200, 400, 409) and time.time() - start < 10


def test_a_nested_tweets_file_is_a_clean_400_not_a_crash(client):
    h = {**login(client), "x-filename": "tweets.js"}
    r = client.post("/api/samples/upload?author_id=1", headers=h, content=b"window.YTD.tweets.part0 = " + b"[" * 100000 + b"tweet" + b"]" * 100000)
    assert r.status_code == 400 and "tweets.js" in r.json()["error"]["message"]
