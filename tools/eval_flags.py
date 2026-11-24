#!/usr/bin/env python3
"""Precision and recall of the house rule and claims checks on the held out drafts (data/eval/heldout_drafts.json).

Draft level: a draft is flagged when the check finds at least one problem. Reports precision, recall and the misses for style and for claims separately.
  python3 tools/eval_flags.py --first-run   save data/eval/flags_first_run.json (refuses to overwrite)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/api/src"))
from penlark import house_rules  # noqa: E402


def run() -> dict:
    drafts = json.loads((ROOT / "data/eval/heldout_drafts.json").read_text())["drafts"]
    rules = house_rules.default_rules()
    rows = []
    for d in drafts:
        notes = {i: n for i, n in enumerate(d["notes"], start=1)}
        r = house_rules.check_all(d["text"], rules, notes)
        rows.append({"id": d["id"], "style_true": d["style_violation"], "style_flag": bool(r["style"]), "claim_true": d["claim_violation"], "claim_flag": bool(r["unsupported_claims"])})
    out = {}
    for k in ("style", "claim"):
        tp = sum(r[f"{k}_true"] and r[f"{k}_flag"] for r in rows)
        fp = sum((not r[f"{k}_true"]) and r[f"{k}_flag"] for r in rows)
        fn = sum(r[f"{k}_true"] and not r[f"{k}_flag"] for r in rows)
        out[k] = {"tp": tp, "fp": fp, "fn": fn, "precision": round(tp / (tp + fp), 3) if tp + fp else None, "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                  "false_positives": [r["id"] for r in rows if not r[f"{k}_true"] and r[f"{k}_flag"]], "misses": [r["id"] for r in rows if r[f"{k}_true"] and not r[f"{k}_flag"]]}
    return {"drafts": len(rows), **out, "note": "Draft level. The phrase list was written by the same team, so unseen wordings are the honest test: the misses show where a paraphrase gets through."}


if __name__ == "__main__":
    res = run()
    out = ROOT / "data/eval/flags_first_run.json"
    if "--first-run" in sys.argv:
        if out.exists():
            sys.exit("flags_first_run.json already exists. The first run is kept untouched.")
        out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
