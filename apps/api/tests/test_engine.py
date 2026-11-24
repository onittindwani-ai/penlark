import json
import time

import pytest
from hypothesis import given, settings, strategies as st

from conftest import DATA, seed_samples
from penlark import experiments, fingerprint, guide, house_rules, ideas, ingest, learning, writers
from penlark.match import match, raw_score
from penlark.textstats import measure, reading_grade, split_sentences, words


@pytest.fixture(scope="module")
def prof():
    return {a: fingerprint.build_profile(seed_samples(a)) for a in ("tobias", "imani", "gareth")}


def test_measure_counts_a_known_text():
    m = measure("We shipped. Don't panic! Is it 5 percent?\n\nYes.")
    assert m.n_sentences == 4 and m.values["questions"] == 0.25 and m.values["contractions"] > 0 and m.values["one_line_paragraphs"] == 0.5


def test_sentence_split_handles_abbreviations_and_decimals():
    assert len(split_sentences("Dr. Smith paid 3.5 dollars. Then left.")) == 2


def test_each_author_scores_highest_on_their_own_training_style(prof):
    own = {"tobias": "We lost a client. Fair. We were late twice.\n\nSo here is the fix. One owner. One update. No exceptions.", "imani": "Have you ever stared at a blank page? I have, and it's okay! Let's try one tiny trick together (it's gentle).",
           "gareth": "It is widely observed that organisations underestimate the cost of delay. Accordingly, we recommend that each decision be assigned to a single accountable executive."}
    for a, t in own.items():
        scores = {b: raw_score(t, prof[b]) for b in prof}
        assert max(scores, key=scores.get) == a, scores


def test_match_reports_per_dimension_advice_and_sentences(prof):
    T = "We lost a client. Fair. In today's fast-paced digital landscape it is important to note that effective communication plays a crucial role in organisational success and stakeholder engagement. One owner per project. No exceptions."
    r = match(T, prof["tobias"])
    assert 0 <= r["score"] <= 100 and r["dimensions"] and r["weakest"] and any(w["advice"] for w in r["weakest"])
    assert r["pull_down"] and r["pull_down"][0]["text"].startswith("In today's") and all(T[p["start"]:p["end"]] == p["text"] for p in r["pull_down"])


def test_match_is_deterministic_and_fast_enough_for_every_keystroke(prof):
    t = " ".join(seed_samples("imani")[:3])
    a, b = match(t, prof["imani"]), match(t, prof["imani"])
    assert {k: v for k, v in a.items() if k != "ms"} == {k: v for k, v in b.items() if k != "ms"}
    t0 = time.perf_counter()
    for _ in range(20):
        match(t, prof["imani"], with_sentences=False)
    assert (time.perf_counter() - t0) / 20 < 0.05  # under 50 ms for about 150 words without the per sentence pass


def test_short_text_is_marked_low_confidence_and_empty_text_is_safe(prof):
    assert match("Hello there friend.", prof["tobias"])["confidence"] == "low"
    assert match("", prof["tobias"])["score"] == 0


@settings(max_examples=60, deadline=None)
@given(st.text(max_size=600))
def test_property_match_never_fails_and_stays_in_range(prof, text):
    r = match(text, prof["gareth"])
    assert 0 <= r["score"] <= 100


@settings(max_examples=40, deadline=None)
@given(st.lists(st.sampled_from(["We shipped it.", "Is it ready?", "Honestly, it's fine!", "It is recommended that the committee defer.", "5 clients paid.\n\n", "ok"]), min_size=1, max_size=12))
def test_property_every_dimension_score_is_in_range(prof, parts):
    for d in match(" ".join(parts), prof["imani"], with_sentences=False)["dimensions"]:
        assert 0 <= d["score"] <= 100


def test_radar_has_one_axis_per_scalar_dimension_and_overlays_a_text(prof):
    base = fingerprint.radar(prof["tobias"])
    over = fingerprint.radar(prof["tobias"], measure("Furthermore, it is recommended that the board act.").values)
    assert len(base) == 14 and all("other" in r for r in over) and all(0 <= r["own"] <= 100 for r in base)


def test_profile_needs_samples_and_lists_signature_words(prof):
    with pytest.raises(ValueError):
        fingerprint.build_profile([])
    assert prof["gareth"]["favourite_words"] and prof["gareth"]["n_samples"] == 16


def test_guide_is_labelled_as_not_a_language_model(prof):
    g = guide.offline_guide(prof["tobias"], "Tobias")
    assert "not a language model" in g and "Never invent facts" in g
    assert "short" in g.lower()


def test_profile_diff_reports_changes_only_when_large(prof):
    assert guide.diff_profiles(prof["tobias"], prof["tobias"]) == []
    assert guide.diff_profiles(prof["tobias"], prof["gareth"])


def test_banned_phrases_patterns_and_dashes_are_flagged():
    r = house_rules.default_rules()
    txt = "Let's dive in. It's not just a tool, it's a game changer — really."
    kinds = {f["kind"] for f in house_rules.check_style(txt, r)}
    assert {"banned_phrase", "banned_pattern", "dash"} <= kinds
    assert house_rules.check_style("Plain words only.", r) == []


def test_reading_level_limit():
    r = house_rules.default_rules()
    r.max_grade = 5.0
    assert any(f["kind"] == "reading_level" for f in house_rules.check_style("Notwithstanding the aforementioned considerations, organisational transformation necessitates comprehensive stakeholder deliberation.", r))


def test_claims_need_a_source_that_contains_the_numbers():
    text = "Marcus got paid in 6 days. I lost a client last year. Plain opinion here."
    flagged = house_rules.check_claims(text, {})
    assert [c["supported"] for c in flagged] == [False, False]
    ok = house_rules.check_claims(text, {8: "Marcus said the first invoice was paid in 6 days instead of 30."})
    assert ok[0]["supported"] and ok[0]["source_note_id"] == 8 and not ok[1]["supported"]
    wrong = house_rules.check_claims("Marcus got paid in 9 days.", {8: "paid in 6 days"})
    assert not wrong[0]["supported"]  # a note that does not contain the number is not a source


def test_experience_claim_is_only_supported_by_an_explicit_link():
    c = house_rules.check_claims("I built the billing in a month.", {3: "Founder note: built billing"}, {"I built the billing in a month.": 3})
    assert c[0]["supported"] is True
    assert house_rules.check_claims("I built the billing in a month.", {3: "x"})[0]["supported"] is False


def test_ingest_formats():
    assert ingest.from_markdown("# Title\n\nSome **bold** [link](http://x.test) text here.").text.startswith("Title")
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello <c>there</c>\n\n2\n00:00:04.000 --> 00:00:06.000\nGeneral Kenobi"
    assert ingest.from_transcript(vtt).text == "Hello there General Kenobi"
    sp = ingest.from_transcript("Ana: I think so.\nBen: Maybe not.\nAna: Fine then.", speaker="ana")
    assert sp.text == "I think so.\nFine then."
    csvd = "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,Visibility\n2026-01-01,x,\"This is a post with enough words in it to count.\",,,MEMBER_NETWORK\n2026-01-02,x,short,,,MEMBER_NETWORK\n"
    assert len(ingest.from_linkedin_csv(csvd)) == 1
    js = 'window.YTD.tweets.part0 = [{"tweet":{"full_text":"RT @a hi","created_at":"x"}},{"tweet":{"full_text":"A real tweet with enough words https://t.co/x","created_at":"Mon Jan 01 2026"}}]'
    assert len(ingest.from_x_archive(js)) == 1
    with pytest.raises(ingest.IngestError):
        ingest.from_pdf(b"not a pdf")
    with pytest.raises(ingest.IngestError):
        ingest.from_linkedin_csv("a,b\n1,2")
    with pytest.raises(ingest.IngestError):
        ingest.detect("big.txt", b"x" * 9_000_000)


def test_idea_evidence_quotes_are_verbatim_and_noise_is_not_an_idea():
    notes = [{**n, "id": int(n["id"][1:])} for n in json.loads(open(f"{DATA}/seed/notes.json").read())]
    src = {n["id"]: n["text"] for n in notes}
    out = ideas.find_ideas(notes)
    assert out
    for i in out:
        for e in i.evidence:
            assert ideas.verify_quote(src[e["note_id"]], e["quote"])
    covered = {nid for i in out for nid in i.note_ids}
    assert not covered & {5, 11, 16, 23, 24}  # logistics, jokes and thanks never become ideas
    assert not ideas.verify_quote("abc def", "abc xyz")


def test_writers_never_invent_and_leave_brackets():
    p = fingerprint.build_profile(seed_samples("imani"))
    v = writers.write(p, {"title": "invoice timing", "evidence": [{"quote": "How soon after finishing work should I invoice?"}]}, "email")
    assert v and "[" in v[0]["text"] and "not a language model" in v[0]["stand_in"]
    assert not any(ch.isdigit() for ch in v[0]["text"])


def test_learning_reports_planted_effect_and_not_the_tiny_sample():
    posts = json.loads(open(f"{DATA}/seed/posts.json").read())
    r = learning.learn(posts)
    by = {t["trait"]: t for t in r["traits"]}
    assert by["uses_emoji"]["status"] == "too_few" and by["uses_emoji"]["lift_percent"] is None
    assert any(t["status"] == "pattern" for t in r["traits"]) and "luck" in r["warnings"][0]
    assert "cause" in next(t for t in r["traits"] if t["status"] == "pattern")["note"]


def test_csv_import_maps_columns_and_reports_bad_rows():
    data = "Date,Views,Reactions,Content\n2026-01-01,1000,50,A post with some words\n2026-01-02,abc,5,Another\n2026-01-03,0,5,Zero views\n"
    m = learning.suggest_mapping(["Date", "Views", "Reactions", "Content"])
    assert m["impressions"] == "Views" and m["likes"] == "Reactions" and m["text"] == "Content"
    rows, problems = learning.parse_csv(data)
    assert len(rows) == 1 and len(problems) == 2
    with pytest.raises(learning.ImportError_):
        learning.parse_csv("a,b\n1,2\n")


def test_experiment_significance_is_honest():
    assert experiments.analyse(300, 30, 300, 52)["verdict"] == "difference"
    assert experiments.analyse(30, 3, 30, 9)["verdict"] == "too_small"
    assert experiments.analyse(1000, 100, 1000, 104)["verdict"] == "no_difference"
    assert experiments.analyse(10, 11, 10, 1)["verdict"] == "invalid"


def test_offline_backend_writes_the_same_variants_and_guide_as_the_rules(prof):
    import json

    from penlark import guide, writers
    from penlark.offline_llm import OfflineBackend
    from sendora_core.safety import wrap_untrusted

    stats = prof["tobias"]
    idea = {"title": "Why invoices go out late", "kind": "post", "variants": 2, "evidence": [{"quote": "Why do invoices go out so late?"}]}
    be = OfflineBackend()
    body = "[task:write_draft]\n" + wrap_untrusted(json.dumps(stats), source="profile") + "\n" + wrap_untrusted(json.dumps(idea), source="idea")
    got = json.loads(be.complete(model="m", system="s", prompt=body, max_tokens=100).text)["variants"]
    want = writers.write(stats, {"title": idea["title"], "evidence": idea["evidence"]}, "post", 2)
    assert [(v["label"], v["text"]) for v in got] == [(v["label"], v["text"]) for v in want] and got
    gp = "[task:write_guide]\n" + wrap_untrusted(json.dumps({**stats, "name": "Tobias"}), source="profile")
    assert json.loads(be.complete(model="m", system="s", prompt=gp, max_tokens=100).text)["guide"] == guide.offline_guide(stats, "Tobias")
    # a broken request gets an empty answer, never an error or a network call
    assert json.loads(be.complete(model="m", system="", prompt="nonsense", max_tokens=10).text) == {}


def test_reading_level_is_not_judged_on_a_very_short_text():
    r = house_rules.Rules([], [], False, 9.0, None, False)
    assert not any(f["kind"] == "reading_level" for f in house_rules.check_style("We synergize quickly.", r))
    long = "Notwithstanding the aforementioned considerations, organisational transformation necessitates comprehensive stakeholder deliberation."
    assert any(f["kind"] == "reading_level" for f in house_rules.check_style(long, r))
    assert house_rules.MIN_WORDS_FOR_GRADE == 8


# ---- round 4: general improvements made after the first independent run (judged on the old sets, never on the independent ones)
def test_banned_phrases_match_hyphens_curly_apostrophes_and_regular_endings():
    from penlark import house_rules as h

    r = h.default_rules()
    kinds = lambda t: [f["text"] for f in h.check_style(t, r) if f["kind"] == "banned_phrase"]  # noqa: E731
    assert kinds("We leveraged it and then we leverage it again.") and kinds("A Game Changer.") == ["Game Changer"] and len(kinds("A game-changer or a game changer.")) == 2
    assert kinds("It’s important to note this.") and kinds("Let us not delve into it. She delves deeper.")
    assert kinds("The sofa is comfortable and the seamstress is kind.") == []  # a near miss word is not a phrase


def test_a_generic_mention_of_a_patient_is_not_a_client_claim_but_a_named_one_is():
    from penlark import house_rules as h

    assert h.find_claims("Tell a patient what to expect and give the family time.") == []
    assert h.find_claims("My patient asked me about it.")[0]["kinds"] == ["client"]
    assert "number" in h.find_claims("We helped ten clients last year.")[0]["kinds"] and "experience" in h.find_claims("We helped ten clients last year.")[0]["kinds"]
    assert "number" in h.find_claims("For ten years we served farmers.")[0]["kinds"]
    assert h.find_claims("Wait two weeks and then check the panel.") == []  # an instruction, not a figure


def test_stemmer_joins_word_forms_and_a_few_everyday_families():
    from penlark import ideas

    assert ideas.stem("stopping") == ideas.stem("stops") == ideas.stem("stop") and ideas.stem("making") == ideas.stem("makes")
    assert ideas.stem("worried") == ideas.stem("afraid") == ideas.stem("dread") and ideas.stem("price") == ideas.stem("costs")
    assert ideas.stem("comfortable") != ideas.stem("comfort")  # a look alike word is not merged
