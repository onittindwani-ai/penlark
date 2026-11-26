#!/usr/bin/env python3
"""The full count check: everything `check_docs.py` checks about counts.json, and the number of Python tests that are collected against the number the docs quote.

  .venv/bin/python tools/check_counts.py

Run it before a pull request. It collects the tests (it does not run them), so it takes a few seconds. After a change that adds or removes tests, run
`.venv/bin/python tools/make_counts.py` (it runs the suite once and writes data/counts.json), then `python3 tools/check_docs.py --fix` to update the numbers in the docs.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import measure  # noqa: E402


def collected() -> int:
    py = ROOT / ".venv" / "bin" / "python"
    p = subprocess.run([str(py) if py.exists() else sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=", "-p", "no:cacheprovider", "-p", "no:warnings"], cwd=ROOT, capture_output=True, text=True)
    m = re.search(r"(\d+) tests? collected", p.stdout)
    if not m:
        raise SystemExit("PROBLEM the tests could not be collected:\n" + (p.stdout + p.stderr)[-600:])
    return int(m.group(1))


def main() -> int:
    counts = json.loads((ROOT / "data" / "counts.json").read_text())
    bad = measure.drift(counts)
    t = counts["tests"]
    n = collected()
    if t["passed"] + t["skipped"] + t["failed"] != n:
        bad.append(f"data/counts.json says {t['passed']} passed, {t['skipped']} skipped and {t['failed']} failed, but {n} tests are collected. Run tools/make_counts.py")
    if t["failed"]:
        bad.append(f"data/counts.json records {t['failed']} failed tests")
    if bad:
        print("\n".join("PROBLEM " + b for b in bad))
        return 1
    print(f"OK counts match the files, and {n} tests are collected as recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
