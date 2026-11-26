#!/usr/bin/env python3
"""Score Penlark on an independent test set (written by separate AI test authors who never saw the code).

A set folder holds `authors.json`, `heldout_texts.json`, `heldout_key.json`, `drafts.json`, `drafts_key.json`, `notes.json` and `ideas_key.json`.
Nothing goes through the database: the profile builder, the voice match, the house rule checker and the idea finder are pure code, and this tool calls them directly,
the way the service does (`fingerprint.build_profile`, `match.match`, `house_rules.check_all` with the system's default rules, `ideas.find_ideas` and `ideas.verify_quote`).
The set's own files are never edited. The keys are read only by the scoring half of this file, after the system has produced its answers.

How the authors' words are read as Penlark's words is fixed here, BEFORE any run of any set:

Voice match.
- One profile per author, built from that author's 20 training samples (all of them, no split).
- A held out text is scored against every profile with `match.match(...)["score"]` (the integer the approval gate uses) and also `raw_score` (exact). The approval threshold is the
  system default `min_voice_match` (60): a text "passes" a profile when its integer score is at least 60.
- top 1 accuracy: over the author texts, the profile with the highest exact score is the text's own author. A tie counts as wrong.
- AUC per author: the chance that a text of that author scores higher on that author's profile than a text of someone else. Two readings are reported. `auc_vs_authors`: the other three
  authors' texts only (this is the look alike test). `auc_vs_all`: every other text, including the outsider and the generic texts.
- look alike pairs from the README, by position in authors.json (the authors are listed 1 to 4): set a (1,3) and (2,4); set b (1,2) and (3,4). For each pair: how many of each
  author's texts score higher on their own profile than on the partner's (pairwise accuracy), and how many are assigned to the partner by top 1 over all four.
- outsider and generic texts: the best of the four scores (exact and integer). Reported: mean best, how many have an integer best score under 60 (what the system would refuse
  to send to approval), the profile each is closest to, and, for generic texts, the profile with the most generic texts assigned.
- the author's own texts against their own profile: how many pass 60 (a gate that refuses real writing would be useless).
- the FULL GATE reading (fixed before any run, because the voice number alone is only half of what the product does): the service marks a draft ready only when the voice match is at
  least 60 AND `house_rules.check_all(...)["ok"]` (no style flag, no unsupported claim; no source notes are attached to a held out text) AND no [BRACKET] placeholder is left. For
  outsider and generic texts, `full_gate_pass` counts the texts whose best score is at least 60 on some profile and that also pass the house rules, and `rules_flagged` counts the
  texts the house rules stop on their own. Both the voice only and the full gate numbers are reported.
- threshold sweep (information only, never used to choose anything): for thresholds 40 to 90 in steps of 5, own texts that pass, outsider and generic texts that pass any profile.

House rules.
- Rules are the system defaults: the built in banned phrases and patterns, dashes banned, reading level maximum from the default setting (grade 9), claims need a source.
- A draft's attached source notes are given to the checker as the notes of the draft (ids 1.. in order). No claim link is made by hand, as a person who had not done it would not.
- A flag kind is `banned_phrase` when any style flag of kind banned_phrase or banned_pattern is raised, `dash` when any dash flag is raised, `reading_level` when a reading level flag is
  raised and `unsourced_claim` when any claim is unsupported.
- The key's `expected` values: true is a plant that must be flagged, false must not be flagged, null (or a missing key) is not scored. Precision and recall per kind are over the
  determinate drafts. Banned phrase recall is reported twice: on the drafts whose planted phrases the authors rated `high` for being in the default list, and on all. A draft with no
  likelihood given counts as high.
- False flags: the drafts of the four categories the README lists as clean (`clean`, `tricky_clean_hyphen_compounds`, `tricky_clean_near_miss_words`, `tricky_clean_sourced_claim`) are counted twice:
  strict (any flag of any kind) and key respecting (only a kind whose `expected` is false; a null such as a borderline reading level is not an error against the key).
- The three ambiguous single drafts and the two `source_mismatch` drafts are reported on their own (what the system did) and are not scored.
- Voice on drafts: the draft is scored against the profile of its `author_id` (skipped for null). Reported for the `in_voice` drafts only: mean score and how many pass 60.

Ideas.
- The 20 notes go to `ideas.find_ideas` (ids 1..20 in order). As in the service, an idea keeps only evidence whose quote is verbatim in its note, and an idea with no verified quote is dropped.
- An idea matches a key theme when at least half of its notes belong to the theme and it holds at least two of the theme's notes. A theme is found when some idea matches it. Reported:
  themes found, note recall per theme, idea purity, ideas that match no theme.
- A decoy (a single note one off) is avoided when no idea holds its note together with fewer than two notes of any theme; a decoy that sits inside a theme's idea is not counted against the
  system. A decoy that outranks a found theme means an idea built around a decoy scores above the best idea of some found theme.
- Quote validity: every evidence quote of every idea is the note's own characters. This holds by construction (a quote is a slice of the note); the informative number is how many raw
  quotes the verbatim filter dropped (`quotes_before_the_verbatim_filter` against `quotes`). Idea purity: for a matched idea, the theme notes it holds divided by all notes it holds. Quotes in the key: the share of evidence quotes that overlap (substring either way) a key supporting quote.

The offline stand in is plain rules, NOT a language model. The first run of a set is saved untouched and is the reported number. Never tune on a set and call it held out.

Run: python tools/eval_independent.py --set a --out data/eval/independent/set_a_first_run.json   (refuses to overwrite an existing file; --check-load only parses the files and prints counts)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "apps" / "api" / "src"), str(ROOT)]

from penlark import house_rules, ideas  # noqa: E402
from penlark.config import Settings  # noqa: E402
from penlark.fingerprint import build_profile  # noqa: E402
from penlark.match import match, raw_score  # noqa: E402

BASE = ROOT / "data" / "eval" / "independent"
LOOKALIKES = {"a": [(0, 2), (1, 3)], "b": [(0, 1), (2, 3)]}
THRESHOLDS = list(range(40, 95, 5))
CLEAN_CATEGORIES = ("clean", "tricky_clean_hyphen_compounds", "tricky_clean_near_miss_words", "tricky_clean_sourced_claim")
KINDS = ("banned_phrase", "dash", "reading_level", "unsourced_claim")
MIN_MATCH = int(Settings.model_fields["min_voice_match"].default)
MAX_GRADE = float(Settings.model_fields["max_reading_grade"].default)


def load(folder: Path) -> dict:
    names = ("authors", "heldout_texts", "heldout_key", "drafts", "drafts_key", "notes", "ideas_key")
    return {n: json.loads((folder / f"{n}.json").read_text(encoding="utf-8")) for n in names}


def auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    return round(sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg)), 3)


def mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


# ------------------------------------------------------------------ voice
def profiles_of(data: dict) -> dict[str, dict]:
    return {a["author_id"]: build_profile([s["text"] for s in a["samples"]]) for a in data["authors"]["authors"]}


def score_voice(data: dict, prof: dict[str, dict], set_letter: str) -> dict:
    ids = [a["author_id"] for a in data["authors"]["authors"]]
    key = data["heldout_key"]
    rows = []
    for t in data["heldout_texts"]:
        exact = {a: raw_score(t["text"], prof[a]) for a in ids}
        whole = {a: match(t["text"], prof[a], with_sentences=False)["score"] for a in ids}
        k = key[t["text_id"]]
        rows.append({"text_id": t["text_id"], "label": k["label"], "author_id": k.get("author_id"), "exact": {a: round(v, 2) for a, v in exact.items()}, "integer": whole})
    for r, t in zip(rows, data["heldout_texts"]):
        res = house_rules.check_all(t["text"], default_rules(), {}, {})
        r["rules_ok"], r["style_flags"] = res["ok"], sorted({f["kind"] for f in res["style"]})
        r["brackets"] = bool(service_brackets(t["text"]))
    by = {"author": [r for r in rows if r["label"] == "author"], "outsider": [r for r in rows if r["label"] == "outsider"], "generic": [r for r in rows if r["label"] == "generic_marketing"]}
    top = lambda r: max(ids, key=lambda a: r["exact"][a])  # noqa: E731
    ties = lambda r: sorted(r["exact"].values())[-1] == sorted(r["exact"].values())[-2]  # noqa: E731
    correct = [r for r in by["author"] if top(r) == r["author_id"] and not ties(r)]
    per_author, confusion = {}, {}
    for a in ids:
        own = [r for r in by["author"] if r["author_id"] == a]
        others = [r for r in by["author"] if r["author_id"] != a]
        rest = [r for r in rows if r not in own]
        for r in own:
            confusion[f"{a}->{top(r)}"] = confusion.get(f"{a}->{top(r)}", 0) + 1
        per_author[a] = {"n": len(own), "top1_correct": sum(1 for r in own if r in correct), "mean_own": mean([r["exact"][a] for r in own]), "mean_other_authors": mean([r["exact"][a] for r in others]),
                         "auc_vs_authors": auc([r["exact"][a] for r in own], [r["exact"][a] for r in others]), "auc_vs_all": auc([r["exact"][a] for r in own], [r["exact"][a] for r in rest]),
                         "own_pass_threshold": sum(1 for r in own if r["integer"][a] >= MIN_MATCH), "own_pass_full_gate": sum(1 for r in own if r["integer"][a] >= MIN_MATCH and r["rules_ok"] and not r["brackets"])}
    pairs = []
    for i, j in LOOKALIKES.get(set_letter, []):
        if max(i, j) >= len(ids):
            continue
        a, b = ids[i], ids[j]
        row = {"pair": [a, b]}
        for x, y in ((a, b), (b, a)):
            own = [r for r in by["author"] if r["author_id"] == x]
            row[x] = {"n": len(own), "higher_on_own_than_partner": sum(1 for r in own if r["exact"][x] > r["exact"][y]), "top1_assigned_to_partner": sum(1 for r in own if top(r) == y)}
        pairs.append(row)

    def best_block(group: list[dict]) -> dict:
        if not group:
            return {"n": 0}
        near = {a: sum(1 for r in group if top(r) == a) for a in ids}
        gate = [r for r in group if max(r["integer"].values()) >= MIN_MATCH and r["rules_ok"] and not r["brackets"]]
        return {"n": len(group), "full_gate_pass": len(gate), "full_gate_pass_ids": [r["text_id"] for r in gate], "rules_flagged": sum(1 for r in group if not r["rules_ok"]),
                "rules_flagged_by_kind": {k: sum(1 for r in group if k in r["style_flags"]) for k in sorted({k for r in group for k in r["style_flags"]})}, "mean_best_exact": mean([max(r["exact"].values()) for r in group]), "mean_best_integer": mean([max(r["integer"].values()) for r in group]),
                "best_below_threshold": sum(1 for r in group if max(r["integer"].values()) < MIN_MATCH), "best_at_or_above_threshold": sum(1 for r in group if max(r["integer"].values()) >= MIN_MATCH),
                "closest_profile_counts": near, "best_scores": sorted(round(max(r["exact"].values()), 1) for r in group)}

    sweep = []
    for th in THRESHOLDS:
        sweep.append({"threshold": th, "own_pass": sum(1 for r in by["author"] if r["integer"][r["author_id"]] >= th), "own_total": len(by["author"]),
                      "outsider_pass_any": sum(1 for r in by["outsider"] if max(r["integer"].values()) >= th), "outsider_total": len(by["outsider"]),
                      "generic_pass_any": sum(1 for r in by["generic"] if max(r["integer"].values()) >= th), "generic_total": len(by["generic"])})
    n_auth = len(by["author"])
    return {"threshold": MIN_MATCH, "author_texts": n_auth, "top1_correct": len(correct), "top1_accuracy": round(len(correct) / n_auth, 3) if n_auth else None,
            "mean_auc_vs_authors": mean_or_none([v["auc_vs_authors"] for v in per_author.values()]), "mean_auc_vs_all": mean_or_none([v["auc_vs_all"] for v in per_author.values()]),
            "own_texts_passing_threshold": sum(v["own_pass_threshold"] for v in per_author.values()), "own_texts_passing_full_gate": sum(v["own_pass_full_gate"] for v in per_author.values()), "per_author": per_author, "confusion": confusion, "lookalike_pairs": pairs,
            "outsider": best_block(by["outsider"]), "generic": best_block(by["generic"]), "threshold_sweep": sweep,
            "wrong_texts": {r["text_id"]: {"author": r["author_id"], "assigned": top(r), "exact": r["exact"]} for r in by["author"] if r not in correct}, "rows": rows}


def service_brackets(text: str) -> list[str]:
    """The placeholder check of `service._brackets` (a draft with a bracket to fill is never ready)."""
    import re

    return re.findall(r"\[[A-Z][A-Z0-9 ,'\-]{2,}[A-Z0-9\]]*\]", text)


def mean_or_none(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


# ------------------------------------------------------------------ house rules
def default_rules() -> house_rules.Rules:
    return house_rules.Rules(list(house_rules.DEFAULT_BANNED), list(house_rules.DEFAULT_PATTERNS), True, MAX_GRADE, None, True)


def raised(text: str, notes: list[dict]) -> tuple[dict[str, bool], dict]:
    res = house_rules.check_all(text, default_rules(), {i + 1: n["text"] for i, n in enumerate(notes)}, {})
    kinds = {f["kind"] for f in res["style"]}
    flags = {"banned_phrase": bool(kinds & {"banned_phrase", "banned_pattern"}), "dash": "dash" in kinds, "reading_level": "reading_level" in kinds, "unsourced_claim": bool(res["unsupported_claims"])}
    return flags, {"grade": res["grade"], "words": res["words"], "style": [(f["kind"], f["text"]) for f in res["style"]][:12], "unsupported": [c["text"][:120] for c in res["unsupported_claims"]]}


def likelihoods(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "likelihood_in_default_list" and isinstance(v, str):
                out.append(v.lower())
            else:
                out += likelihoods(v)
    elif isinstance(obj, list):
        for v in obj:
            out += likelihoods(v)
    return out


def prf(tp: int, fp: int, fn: int) -> dict:
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(tp / (tp + fp), 3) if tp + fp else None, "recall": round(tp / (tp + fn), 3) if tp + fn else None}


def score_flags(data: dict, prof: dict[str, dict]) -> dict:
    key = data["drafts_key"]
    recs = []
    for d in data["drafts"]:
        k = key[d["draft_id"]]
        flags, info = raised(d["text"], d.get("attached_source_notes") or [])
        voice = None
        if d.get("author_id") in prof:
            voice = match(d["text"], prof[d["author_id"]], with_sentences=False)["score"]
        recs.append({"draft_id": d["draft_id"], "category": k["category"], "expected": {x: (k.get("expected") or {}).get(x) for x in KINDS}, "flags": flags, "voice_expected": k.get("voice_expected"), "voice_score": voice,
                     "likelihoods": likelihoods(k.get("details", {}).get("banned_phrase") if isinstance(k.get("details"), dict) and "banned_phrase" in k["details"] else k.get("details", {})), **info})
    per_kind = {}
    for kind in KINDS:
        scored = [r for r in recs if r["expected"][kind] is not None]
        tp = sum(1 for r in scored if r["expected"][kind] and r["flags"][kind])
        fp = sum(1 for r in scored if not r["expected"][kind] and r["flags"][kind])
        fn = sum(1 for r in scored if r["expected"][kind] and not r["flags"][kind])
        per_kind[kind] = {"scored": len(scored), **prf(tp, fp, fn), "missed": [r["draft_id"] for r in scored if r["expected"][kind] and not r["flags"][kind]], "false": [r["draft_id"] for r in scored if not r["expected"][kind] and r["flags"][kind]]}
    high = [r for r in recs if r["expected"]["banned_phrase"] and all(x == "high" for x in r["likelihoods"])]
    per_kind["banned_phrase"]["recall_on_high_likelihood"] = {"planted": len(high), "found": sum(1 for r in high if r["flags"]["banned_phrase"]), "missed": [r["draft_id"] for r in high if not r["flags"]["banned_phrase"]]}
    clean = [r for r in recs if r["category"] in CLEAN_CATEGORIES]
    by_cat: dict[str, dict] = {}
    for r in clean:
        c = by_cat.setdefault(r["category"], {"n": 0, "falsely_flagged_strict": 0, "falsely_flagged_key_respecting": 0, "which": []})
        c["n"] += 1
        strict = [k for k, v in r["flags"].items() if v]
        keyed = [k for k in strict if r["expected"][k] is False]
        c["falsely_flagged_strict"] += bool(strict)
        c["falsely_flagged_key_respecting"] += bool(keyed)
        if strict:
            c["which"].append({"draft_id": r["draft_id"], "kinds": strict, "kinds_the_key_says_false": keyed})
    ambiguous = [{"draft_id": r["draft_id"], "category": r["category"], "flags": r["flags"], "expected": r["expected"]} for r in recs if "ambig" in r["category"] or r["category"].startswith("single")]
    mism = [{"draft_id": r["draft_id"], "unsourced_flagged": r["flags"]["unsourced_claim"], "unsupported": r["unsupported"]} for r in recs if r["category"] == "source_mismatch"]
    invoice = [r for r in recs if r["voice_expected"] == "in_voice" and r["voice_score"] is not None]
    categories: dict[str, int] = {}
    for r in recs:
        categories[r["category"]] = categories.get(r["category"], 0) + 1
    return {"drafts": len(recs), "categories": categories, "per_kind": per_kind, "clean_drafts": len(clean), "clean_falsely_flagged_strict": sum(1 for r in clean if any(r["flags"].values())),
            "clean_falsely_flagged_key_respecting": sum(1 for r in clean if any(r["flags"][k] and r["expected"][k] is False for k in KINDS)), "clean_by_category": by_cat,
            "ambiguous_singles": ambiguous, "source_mismatch": mism,
            "voice_in_voice_drafts": {"n": len(invoice), "mean_score": mean([r["voice_score"] for r in invoice]), "passing_threshold": sum(1 for r in invoice if r["voice_score"] >= MIN_MATCH)}, "rows": recs}


# ------------------------------------------------------------------ ideas
def overlaps(a: str, b: str) -> bool:
    a, b = " ".join(a.split()).lower(), " ".join(b.split()).lower()
    return bool(a and b and (a in b or b in a))


def note_ids_of(obj, known: set[str]) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, str):
        if obj in known:
            out.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= note_ids_of(v, known)
    elif isinstance(obj, list):
        for v in obj:
            out |= note_ids_of(v, known)
    return out


def score_ideas(data: dict) -> dict:
    notes = data["notes"]
    num = {n["note_id"]: i + 1 for i, n in enumerate(notes)}
    name = {v: k for k, v in num.items()}
    text = {num[n["note_id"]]: n["text"] for n in notes}
    found = ideas.find_ideas([{"id": num[n["note_id"]], "kind": n.get("kind", "note"), "text": n["text"]} for n in notes])
    kept = []
    for i in found:
        ev = [e for e in i.evidence if ideas.verify_quote(text[e["note_id"]], e["quote"])]
        if ev:
            kept.append((i, ev))
    key = data["ideas_key"]
    themes = [{"theme_id": t["theme_id"], "title": t.get("title", ""), "notes": {num[x] for x in t["note_ids"] if x in num}, "quotes": [q["quote"] for q in t.get("supporting_quotes", [])]} for t in key["themes"]]
    known = set(num)
    decoys = [{"notes": {num[x] for x in note_ids_of(d, known)}, "raw": d} for d in key.get("decoys", [])]
    ranks = {id(i): r + 1 for r, (i, _e) in enumerate(kept)}
    matches: dict[str, dict] = {}
    for t in themes:
        best = None
        for i, _e in kept:
            inside = set(i.note_ids) & t["notes"]
            if len(inside) >= 2 and len(inside) * 2 >= len(i.note_ids) and (best is None or len(inside) > best[0]):
                best = (len(inside), i)
        matches[t["theme_id"]] = {"found": best is not None, "note_recall": round(best[0] / len(t["notes"]), 2) if best else 0.0, "idea_title": best[1].title if best else None, "rank": ranks[id(best[1])] if best else None,
                                  "purity": round(best[0] / len(best[1].note_ids), 2) if best else None, "score": best[1].score if best else None, "idea_notes": [name[x] for x in best[1].note_ids] if best else []}
    matched_ids = {id(m_i) for t in themes for m_i, _e in kept if set(m_i.note_ids) & t["notes"] and len(set(m_i.note_ids) & t["notes"]) >= 2 and len(set(m_i.note_ids) & t["notes"]) * 2 >= len(m_i.note_ids)}
    unmatched = [(i, e) for i, e in kept if id(i) not in matched_ids]
    best_found_scores = [m["score"] for m in matches.values() if m["found"]]
    decoy_rows = []
    for d in decoys:
        holders = [i for i, _e in kept if set(i.note_ids) & d["notes"]]
        lone = [i for i in holders if not any(len(set(i.note_ids) & t["notes"]) >= 2 for t in themes)]
        decoy_rows.append({"notes": sorted(name[x] for x in d["notes"]), "in_an_idea": len(holders), "in_a_non_theme_idea": len(lone), "avoided": not lone,
                           "outranks_a_found_theme": any(best_found_scores and i.score > min(best_found_scores) for i in lone)})
    n_q = sum(len(e) for _i, e in kept)
    all_key_quotes = [q for t in themes for q in t["quotes"]]
    in_key = sum(1 for _i, e in kept for q in e if any(overlaps(q["quote"], k) for k in all_key_quotes))
    raw_quotes = sum(len(i.evidence) for i in found)
    return {"ideas_returned": len(found), "ideas_with_verified_quote": len(kept), "themes_total": len(themes), "themes_found": sum(1 for m in matches.values() if m["found"]), "per_theme": matches,
            "ideas_matching_no_theme": [{"title": i.title, "notes": [name[x] for x in i.note_ids], "score": i.score, "rank": ranks[id(i)]} for i, _e in unmatched],
            "decoys_total": len(decoys), "decoys_avoided": sum(1 for r in decoy_rows if r["avoided"]), "decoys_outranking_a_found_theme": sum(1 for r in decoy_rows if r["outranks_a_found_theme"]), "decoys": decoy_rows,
            "quotes": n_q, "quotes_verbatim": sum(1 for _i, e in kept for q in e if q["quote"] in text[q["note_id"]]), "quotes_before_the_verbatim_filter": raw_quotes, "quotes_overlapping_a_key_quote": in_key,
            "ranked": [{"rank": ranks[id(i)], "title": i.title, "notes": [name[x] for x in i.note_ids], "score": i.score} for i, _e in kept]}


def run(folder: Path, set_letter: str) -> dict:
    data = load(folder)
    prof = profiles_of(data)
    return {"set": set_letter, "folder": folder.name, "settings": {"min_voice_match": MIN_MATCH, "max_reading_grade": MAX_GRADE, "no_dashes": True, "require_sources": True},
            "voice": score_voice(data, prof, set_letter), "flags": score_flags(data, prof), "ideas": score_ideas(data),
            "note": "Scores come from plain code (profile statistics, rule lists, word counts), not a language model. The texts are sample data and assembled from sentence banks."}


def summary(res: dict) -> dict:
    v, f, i = res["voice"], res["flags"], res["ideas"]
    return {"set": res["set"], "voice": {k: v[k] for k in ("author_texts", "top1_correct", "top1_accuracy", "mean_auc_vs_authors", "mean_auc_vs_all", "own_texts_passing_threshold")},
            "own_texts_passing_full_gate": v["own_texts_passing_full_gate"], "outsider": {k: v["outsider"].get(k) for k in ("n", "mean_best_exact", "best_below_threshold", "full_gate_pass", "rules_flagged")},
            "generic": {k: v["generic"].get(k) for k in ("n", "mean_best_exact", "best_below_threshold", "full_gate_pass", "rules_flagged", "rules_flagged_by_kind", "closest_profile_counts")},
            "flags": {k: {x: f["per_kind"][k].get(x) for x in ("precision", "recall", "tp", "fp", "fn")} for k in KINDS}, "clean_falsely_flagged_strict": f"{f['clean_falsely_flagged_strict']} of {f['clean_drafts']}", "clean_falsely_flagged_key_respecting": f"{f['clean_falsely_flagged_key_respecting']} of {f['clean_drafts']}",
            "ideas": {k: i[k] for k in ("themes_found", "themes_total", "decoys_avoided", "decoys_total", "quotes", "quotes_verbatim")}}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["a", "b"], required=True)
    ap.add_argument("--folder", help="folder with the set files (default data/eval/independent/set_<x>)")
    ap.add_argument("--out", help="write the full result here (refuses to overwrite)")
    ap.add_argument("--check-load", action="store_true")
    a = ap.parse_args(argv)
    folder = Path(a.folder) if a.folder else BASE / f"set_{a.set}"
    if a.check_load:
        d = load(folder)
        print(json.dumps({"authors": len(d["authors"]["authors"]), "samples_per_author": [len(x["samples"]) for x in d["authors"]["authors"]], "heldout_texts": len(d["heldout_texts"]), "drafts": len(d["drafts"]), "notes": len(d["notes"]), "themes": len(d["ideas_key"]["themes"])}))
        return 0
    if a.out and Path(a.out).exists():
        sys.exit(f"{a.out} already exists. A first run is kept untouched.")
    res = run(folder, a.set)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
        print("saved", a.out)
    print(json.dumps(summary(res), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
