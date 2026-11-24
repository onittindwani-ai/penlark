#!/usr/bin/env python3
"""Idea finder sanity check on the held out notes (data/eval/heldout_notes.json) and on the seed notes (a development set, tuned on).

For each set: how many planted themes were found as a top idea, how many noise notes leaked into an idea, and whether every evidence quote is verbatim (must be 100 percent).
  python3 tools/eval_ideas.py --first-run   save data/eval/ideas_first_run.json (refuses to overwrite)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/api/src"))
from penlark.ideas import find_ideas, verify_quote  # noqa: E402


def score(notes: list[dict], themes: dict[str, list[int]], noise: list[int]) -> dict:
    src = {n["id"]: n["text"] for n in notes}
    ideas = find_ideas(notes)
    quotes = [(e["note_id"], e["quote"]) for i in ideas for e in i.evidence]
    valid = sum(verify_quote(src[nid], q) for nid, q in quotes)
    found = {}
    for name, ids in themes.items():
        best = max(((len(set(i.note_ids) & set(ids)) / len(i.note_ids), len(set(i.note_ids) & set(ids)) / len(ids), rank) for rank, i in enumerate(ideas)), default=(0, 0, -1))
        # a theme is found when one idea holds mostly its notes (purity at least 0.6) and covers at least half of them
        hits = [(rank, i) for rank, i in enumerate(ideas) if len(set(i.note_ids) & set(ids)) / len(i.note_ids) >= 0.6 and len(set(i.note_ids) & set(ids)) / len(ids) >= 0.5]
        found[name] = {"found": bool(hits), "rank": hits[0][0] + 1 if hits else None}
    leaked = sorted({nid for i in ideas for nid in i.note_ids if nid in noise})
    top3 = ideas[:3]
    return {"ideas": len(ideas), "themes": found, "themes_found": sum(v["found"] for v in found.values()), "themes_total": len(themes), "noise_leaked": leaked, "quotes": len(quotes), "quotes_valid": valid,
            "top3_are_themes": sum(any(len(set(i.note_ids) & set(ids)) / len(i.note_ids) >= 0.6 for ids in themes.values()) for i in top3), "top3_titles": [i.title for i in top3]}


def run() -> dict:
    h = json.loads((ROOT / "data/eval/heldout_notes.json").read_text())
    d = json.loads((ROOT / "data/seed/notes.json").read_text())
    key = json.loads((ROOT / "data/seed/notes_key.json").read_text())
    dev_notes = [{**n, "id": int(n["id"][1:])} for n in d]
    dev_themes = {k: [int(x[1:]) for x in v] for k, v in key["themes"].items()}
    return {"heldout": score(h["notes"], h["themes"], h["noise"]), "development": score(dev_notes, dev_themes, [int(x[1:]) for x in key["noise"]]),
            "note": "The development set was used while the finder was built. Only the held out numbers are honest. Quote validity must be 100 percent on both."}


if __name__ == "__main__":
    res = run()
    out = ROOT / "data/eval/ideas_first_run.json"
    if "--first-run" in sys.argv:
        if out.exists():
            sys.exit("ideas_first_run.json already exists. The first run is kept untouched.")
        out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
