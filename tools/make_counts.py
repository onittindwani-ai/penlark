#!/usr/bin/env python3
"""Measure the numbers the docs quote and write them to data/counts.json.

Every count in README and docs/ comes from this file. Run it after any change, then run tools/check_docs.py.
  python3 tools/make_counts.py            measure and write (runs the Python tests once, with coverage)
  python3 tools/make_counts.py --fast     skip the test run and keep the last test and coverage numbers
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "counts.json"
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable
sys.path.insert(0, str(ROOT / "apps/api/src"))


def run_tests() -> dict:
    cov = ROOT / ".coverage-counts.json"
    p = subprocess.run([PY, "-m", "pytest", "apps/api/tests", "mock/tests", "tools/tests", "-o", "addopts=", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", "--cov=penlark", f"--cov-report=json:{cov}"], cwd=ROOT, capture_output=True, text=True)
    m, sk, fl = (re.search(rf"(\d+) {w}", p.stdout) for w in ("passed", "skipped", "failed"))
    pct = None
    if cov.exists():
        pct = round(json.loads(cov.read_text())["totals"]["percent_covered"], 1)
        cov.unlink()
    return {"passed": int(m.group(1)) if m else 0, "skipped": int(sk.group(1)) if sk else 0, "failed": int(fl.group(1)) if fl else 0, "coverage_percent": pct}


def main(argv: list[str]) -> int:
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    sd, ev = ROOT / "data" / "seed", ROOT / "data" / "eval"
    from penlark import house_rules

    per = {a: len(json.loads((sd / f"samples_{a}.json").read_text())) for a in ("tobias", "imani", "gareth")}
    links = json.loads((sd / "links.json").read_text())
    held = json.loads((ev / "heldout_texts.json").read_text())["texts"]
    seed = {"authors": len(per), "samples_total": sum(per.values()), "samples_per_author": min(per.values()), "notes": len(json.loads((sd / "notes.json").read_text())), "posts": len(json.loads((sd / "posts.json").read_text())),
            "links": len(links["links"]), "clicks": len(links["clicks"]), "conversions": len(links["conversions"]), "experiments": len(json.loads((sd / "experiments.json").read_text())),
            "heldout_texts": len(held), "heldout_drafts": len(json.loads((ev / "heldout_drafts.json").read_text())["drafts"]), "heldout_notes": len(json.loads((ev / "heldout_notes.json").read_text())["notes"]),
            "banned_phrases": len(house_rules.DEFAULT_BANNED), "banned_patterns": len(house_rules.DEFAULT_PATTERNS)}
    v, f, i = (json.loads((ev / n).read_text()) for n in ("voice_first_run.json", "flags_first_run.json", "ideas_first_run.json"))
    evals = {"voice": {"correct": v["top1_correct"], "of": v["author_texts"], "auc": v["mean_auc"], "generic_mean_best": v["per_class"]["generic"]["mean_best_score"], "outsider_mean_best": v["per_class"]["noor"]["mean_best_score"]},
             "flags": {"style_precision": f["style"]["precision"], "style_recall": f["style"]["recall"], "claim_precision": f["claim"]["precision"], "claim_recall": f["claim"]["recall"]},
             "ideas": {"themes_found": i["heldout"]["themes_found"], "themes_total": i["heldout"]["themes_total"], "noise_leaked": len(i["heldout"]["noise_leaked"]), "quotes_valid": i["heldout"]["quotes_valid"], "quotes": i["heldout"]["quotes"]}}
    ind = {}
    for key, fn in (("a_first", "set_a_first_run"), ("a_after", "set_a_after_improvements"), ("b_first", "set_b_first_run")):
        r = json.loads((ev / "independent" / f"{fn}.json").read_text())
        vo, fl, idd = r["voice"], r["flags"]["per_kind"], r["ideas"]
        ind[key] = {"top1": vo["top1_correct"], "authors_texts": vo["author_texts"], "auc_authors": vo["mean_auc_vs_authors"], "auc_all": vo["mean_auc_vs_all"], "own_full_gate": vo["own_texts_passing_full_gate"],
                    "outsider_mean_best": vo["outsider"]["mean_best_exact"], "outsider_below": vo["outsider"]["best_below_threshold"], "outsider_full_gate": vo["outsider"]["full_gate_pass"],
                    "generic_mean_best": vo["generic"]["mean_best_exact"], "generic_below": vo["generic"]["best_below_threshold"], "generic_full_gate": vo["generic"]["full_gate_pass"],
                    "banned_found": fl["banned_phrase"]["tp"], "banned_planted": fl["banned_phrase"]["tp"] + fl["banned_phrase"]["fn"], "claim_found": fl["unsourced_claim"]["tp"], "claim_planted": fl["unsourced_claim"]["tp"] + fl["unsourced_claim"]["fn"],
                    "claim_false": fl["unsourced_claim"]["fp"], "reading_false": fl["reading_level"]["fp"], "themes_found": idd["themes_found"], "themes_total": idd["themes_total"], "decoys_avoided": idd["decoys_avoided"], "decoys_total": idd["decoys_total"]}
    count_tests = lambda f: len(re.findall(r"^def test_", (ROOT / f).read_text(), re.M))  # noqa: E731
    model = {"tests": count_tests("apps/api/tests/test_model_path.py"), "fixtures": len(list((ROOT / "data" / "llm_fixtures").glob("*.json"))), "contract_tests": count_tests("mock/tests/test_contracts.py")}
    api = json.loads((ROOT / "docs" / "openapi.json").read_text())
    ops = sum(1 for vv in api["paths"].values() for k in vv if k in ("get", "post", "put", "patch", "delete"))
    tables = len(re.findall(r'__tablename__ = "vp_', (ROOT / "apps/api/src/penlark/models.py").read_text()))
    lst = subprocess.run(["pnpm", "exec", "playwright", "test", "--list"], cwd=ROOT / "apps" / "web", capture_output=True, text=True).stdout
    mm = re.search(r"Total: (\d+) tests? in (\d+) files?", lst)
    e2e = {"tests": int(mm.group(1)), "files": int(mm.group(2))} if mm else old.get("e2e")
    scores = json.loads((ROOT / "data" / "tool_scores.json").read_text())
    pages = len(re.findall(r'id: "/', (ROOT / "apps/web/src/components/AppFrame.tsx").read_text()))
    shots = len(list((ROOT / "docs" / "screenshots").glob("*.png")))
    tests = old.get("tests") if "--fast" in argv else run_tests()
    data = {"tables": tables, "api_paths": len(api["paths"]), "api_operations": ops, "pages": pages, "screenshots": shots, "tool_groups": len(scores["groups"]), "tools_scored": sum(len(g["tools"]) for g in scores["groups"]),
            "dimensions": 14, "seed": seed, "eval": evals, "independent": ind, "model": model, "e2e": e2e, "tests": tests}
    OUT.write_text(json.dumps(data, indent=1) + "\n")
    print("OK wrote", OUT.relative_to(ROOT), json.dumps({k: data[k] for k in ("tables", "api_paths", "pages", "screenshots", "tools_scored", "tests")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
