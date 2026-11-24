#!/usr/bin/env python3
"""Voice match evaluation on the held out texts (data/eval/heldout_texts.json), written before the match code.

For each of three fictional authors a profile is built from that author's training samples. Every held out text is scored against every profile.
Reported: top 1 accuracy for the three authors, the confusion pairs, the mean score own against others, and an AUC (the chance that a text by the author scores
higher on the author's profile than a text by someone else). Outsider texts (a fourth author) and generic machine sounding texts are shown separately.

  python3 tools/eval_voice.py --first-run   write data/eval/voice_first_run.json (refuses to overwrite it: the first run is kept untouched)
  python3 tools/eval_voice.py               run again and print, never writes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/api/src"))
from penlark.fingerprint import build_profile  # noqa: E402
from penlark.match import raw_score  # noqa: E402

AUTHORS = ("tobias", "imani", "gareth")


def auc(pos: list[float], neg: list[float]) -> float:
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def run() -> dict:
    prof = {a: build_profile(json.loads((ROOT / f"data/seed/samples_{a}.json").read_text())) for a in AUTHORS}
    texts = json.loads((ROOT / "data/eval/heldout_texts.json").read_text())["texts"]
    scores = {t["id"]: {a: raw_score(t["text"], prof[a]) for a in AUTHORS} for t in texts}
    by_label: dict[str, list[dict]] = {}
    for t in texts:
        by_label.setdefault(t["label"], []).append(t)
    per_class, confusion = {}, {}
    for a in AUTHORS:
        own = by_label[a]
        top = [max(AUTHORS, key=lambda x: scores[t["id"]][x]) for t in own]
        for p in top:
            confusion[f"{a}->{p}"] = confusion.get(f"{a}->{p}", 0) + 1
        pos = [scores[t["id"]][a] for t in own]
        neg = [scores[t["id"]][a] for t in texts if t["label"] != a]
        per_class[a] = {"n": len(own), "top1_correct": sum(p == a for p in top), "top1_accuracy": round(sum(p == a for p in top) / len(own), 3), "mean_own": round(sum(pos) / len(pos), 1), "mean_others": round(sum(neg) / len(neg), 1), "auc": round(auc(pos, neg), 3)}
    for lab in ("noor", "generic"):
        top = [max(AUTHORS, key=lambda x: scores[t["id"]][x]) for t in by_label[lab]]
        per_class[lab] = {"n": len(top), "assigned_to": {a: top.count(a) for a in AUTHORS}, "mean_best_score": round(sum(max(scores[t["id"]].values()) for t in by_label[lab]) / len(top), 1)}
    n_auth = sum(per_class[a]["n"] for a in AUTHORS)
    ok = sum(per_class[a]["top1_correct"] for a in AUTHORS)
    wrong = {t["id"]: {a: round(v, 1) for a, v in scores[t["id"]].items()} for t in texts if t["label"] in AUTHORS and max(AUTHORS, key=lambda x: scores[t["id"]][x]) != t["label"]}
    return {"texts": len(texts), "author_texts": n_auth, "top1_correct": ok, "top1_accuracy": round(ok / n_auth, 3), "mean_auc": round(sum(per_class[a]["auc"] for a in AUTHORS) / 3, 3), "per_class": per_class, "confusion": confusion, "wrong_texts": wrong,
            "note": "Match scores come from code, not a language model. Texts are short (30 to 90 words) and every text is fictional."}


if __name__ == "__main__":
    res = run()
    out = ROOT / "data/eval/voice_first_run.json"
    if "--first-run" in sys.argv:
        if out.exists():
            sys.exit("voice_first_run.json already exists. The first run is kept untouched.")
        out.write_text(json.dumps(res, indent=1) + "\n")
        print("saved first run")
    print(json.dumps({k: res[k] for k in ("top1_correct", "author_texts", "top1_accuracy", "mean_auc")}), json.dumps(res["per_class"]), res["confusion"], res["wrong_texts"])
