"""Tests for the independent evaluation tool on a tiny made up set (NOT one of the held out sets)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import eval_independent as ei  # noqa: E402

PLAIN = ["Short lines win. I keep it plain. You read it once.", "Plain words work. I say what I mean. Then I stop.", "We ship on Monday. It is done. You get the file."]
LONG = ["The committee considered the proposal at length, and the members agreed that further analysis would be prudent before any commitment was made.",
        "Where the evidence is incomplete, the responsible course is to defer the decision, while documenting the assumptions that remain untested.",
        "In the circumstances described, a measured and thorough review of the underlying obligations seems entirely appropriate and necessary."]


def build(tmp: Path) -> Path:
    authors = [{"author_id": f"X{i}", "name": f"Author {i}", "profession": "tester", "register_note": "", "samples": [{"sample_id": f"X{i}s{j}", "text": (PLAIN if i % 2 else LONG)[j % 3] + " " + (PLAIN if i % 2 else LONG)[(j + 1) % 3] + f" Marker {i}."} for j in range(6)]} for i in range(1, 5)]
    texts = [{"text_id": "T1", "text": PLAIN[0] + " " + PLAIN[1]}, {"text_id": "T2", "text": LONG[0] + " " + LONG[1]}, {"text_id": "T3", "text": "In today's fast-paced world, unlock the power of seamless synergy for your business and take it to the next level."}]
    key = {"T1": {"label": "author", "author_id": "X1"}, "T2": {"label": "author", "author_id": "X2"}, "T3": {"label": "generic_marketing"}}
    drafts = [{"draft_id": "D1", "author_id": "X1", "text": "We ship on Monday. It is done. You get the file today.", "attached_source_notes": []},
              {"draft_id": "D2", "author_id": "X1", "text": "We ship on Monday — it is done. You get the file today and we are glad.", "attached_source_notes": []},
              {"draft_id": "D3", "author_id": "X1", "text": "We tested it on 450 customers and it saved them time. You get the file today.", "attached_source_notes": []},
              {"draft_id": "D4", "author_id": "X1", "text": "We tested it on 450 customers and it saved them time. You get the file today.", "attached_source_notes": [{"note_id": "n1", "text": "Pilot with 450 customers last spring."}]}]
    exp = lambda b, d, r, u: {"banned_phrase": b, "dash": d, "reading_level": r, "unsourced_claim": u}  # noqa: E731
    dkey = {"D1": {"category": "clean", "voice_expected": "in_voice", "expected": exp(False, False, False, False)}, "D2": {"category": "dash", "voice_expected": None, "expected": exp(False, True, None, False)},
            "D3": {"category": "unsourced_claim", "voice_expected": None, "expected": exp(False, False, False, True)}, "D4": {"category": "tricky_clean_sourced_claim", "voice_expected": None, "expected": exp(False, False, False, False)}}
    notes = [{"note_id": f"N{i}", "kind": "call", "source_label": "x", "text": t} for i, t in enumerate([
        "Clients keep asking how to write the follow up message after a missed invoice payment. It feels awkward to push.",
        "Another client asked how to word the follow up after an unpaid invoice. They are afraid of sounding rude.",
        "Someone wrote that the follow up on an overdue invoice is the part they dread most every month.",
        "The printer paper arrived on Tuesday and the calendar sync is working now, thanks for the help.",
        "We moved the standing meeting to Thursday afternoon and see you there.",
        "Thanks, the charger is back and the dentist moved the appointment."], 1)]
    ikey = {"notes_for_author": "X1", "themes": [{"theme_id": "TH1", "title": "invoice follow up", "note_ids": ["N1", "N2", "N3"], "supporting_quotes": [{"note_id": "N1", "quote": "It feels awkward to push."}]}], "decoys": [{"note_id": "N4"}]}
    d = tmp / "set_t"
    d.mkdir()
    for name, obj in (("authors", {"set": "t", "authors": authors}), ("heldout_texts", texts), ("heldout_key", key), ("drafts", drafts), ("drafts_key", dkey), ("notes", notes), ("ideas_key", ikey)):
        (d / f"{name}.json").write_text(json.dumps(obj))
    return d


def test_the_tool_scores_a_tiny_set_and_keeps_its_readings(tmp_path):
    res = ei.run(build(tmp_path), "a")
    v, f, i = res["voice"], res["flags"], res["ideas"]
    assert v["author_texts"] == 2 and v["top1_correct"] + len(v["wrong_texts"]) == 2 and v["generic"]["n"] == 1 and len(v["threshold_sweep"]) == len(ei.THRESHOLDS)
    assert f["per_kind"]["dash"]["tp"] == 1 and f["per_kind"]["dash"]["fp"] == 0
    assert f["per_kind"]["unsourced_claim"]["tp"] == 1 and f["per_kind"]["unsourced_claim"]["fp"] == 0  # the sourced twin (D4) is not flagged
    assert f["clean_drafts"] == 2 and f["clean_falsely_flagged_strict"] == 0 and f["clean_falsely_flagged_key_respecting"] == 0
    assert i["themes_total"] == 1 and i["themes_found"] == 1 and i["quotes"] == i["quotes_verbatim"] > 0


def test_a_generic_text_with_stock_phrases_is_flagged_by_the_rules(tmp_path):
    flags, info = ei.raised("In today's fast-paced world, unlock the power of seamless synergy and take it to the next level.", [])
    assert flags["banned_phrase"] and not flags["dash"] and info["words"] > 8


def test_overlap_and_note_id_helpers():
    assert ei.overlaps("It feels  awkward", "so it feels awkward to push") and not ei.overlaps("", "x")
    assert ei.note_ids_of({"a": ["N1", {"b": "N9"}], "c": "zzz"}, {"N1", "N9"}) == {"N1", "N9"}
    assert ei.auc([2, 3], [1, 2]) == 0.875 and ei.auc([], [1]) is None
    assert ei.likelihoods({"x": [{"likelihood_in_default_list": "High"}, {"likelihood_in_default_list": "medium"}]}) == ["high", "medium"]


def test_a_first_run_file_is_never_overwritten(tmp_path):
    folder = build(tmp_path)
    out = tmp_path / "first.json"
    assert ei.main(["--set", "a", "--folder", str(folder), "--out", str(out)]) == 0 and out.exists()
    with pytest.raises(SystemExit):
        ei.main(["--set", "a", "--folder", str(folder), "--out", str(out)])


def test_check_load_counts(tmp_path, capsys):
    assert ei.main(["--set", "b", "--folder", str(build(tmp_path)), "--check-load"]) == 0
    assert json.loads(capsys.readouterr().out)["authors"] == 4


def test_full_gate_and_idea_purity(tmp_path):
    res = ei.run(build(tmp_path), "a")
    g = res["voice"]["generic"]
    assert g["n"] == 1 and g["rules_flagged"] == 1 and g["full_gate_pass"] == 0 and "banned_phrase" in g["rules_flagged_by_kind"]
    assert res["ideas"]["per_theme"]["TH1"]["purity"] == 1.0
