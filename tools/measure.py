"""Numbers that can be read straight from the files, with no test run and no browser: the tables, the API paths and operations, the pages, the screenshots, the scored tools.

`check_docs.py` compares them with data/counts.json (and so with every quoted count in the docs), so a count cannot drift when a route, a table or a page is added.
Standard library only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def operations(spec: dict) -> int:
    return sum(1 for v in spec["paths"].values() for k in v if k in ("get", "post", "put", "patch", "delete"))


def cheap_counts() -> dict:
    spec = json.loads((ROOT / "docs" / "openapi.json").read_text())
    scores = json.loads((ROOT / "data" / "tool_scores.json").read_text())
    return {
        "tables": len(re.findall(r'__tablename__ = "vp_', (ROOT / "apps/api/src/penlark/models.py").read_text())),
        "api_paths": len(spec["paths"]),
        "api_operations": operations(spec),
        "pages": len(re.findall(r'id: "/', (ROOT / "apps/web/src/components/AppFrame.tsx").read_text())),
        "screenshots": len(list((ROOT / "docs" / "screenshots").glob("*.png"))),
        "tool_groups": len(scores["groups"]),
        "tools_scored": sum(len(g["tools"]) for g in scores["groups"]),
    }


def drift(counts: dict) -> list[str]:
    """Where data/counts.json disagrees with the files. Empty when it is current."""
    return [f"data/counts.json says {k} is {counts.get(k)}, the files say {v}. Run python3 tools/make_counts.py" for k, v in cheap_counts().items() if counts.get(k) != v]
