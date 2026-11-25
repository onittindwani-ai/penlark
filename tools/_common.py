"""Shared bits for the tools: put the sources on the path, and make sure the project's own Python is the one running.

On a fresh clone `python3 tools/doctor.py` works: if the packages are not importable and `.venv` exists (`make install` made it), the tool starts again with `.venv/bin/python`.
With no `.venv` it stops with one plain sentence instead of a stack trace.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "core-py" / "src"))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
sys.path.insert(0, str(ROOT))


def _venv_python() -> Path | None:
    for rel in (".venv/bin/python", ".venv/Scripts/python.exe"):
        p = ROOT / rel
        if p.exists():
            return p
    return None


def ensure_project_python() -> None:
    try:
        import argon2  # noqa: F401
        import pydantic  # noqa: F401
        import sendora_core  # noqa: F401
        import sqlalchemy  # noqa: F401
    except ImportError:
        venv = _venv_python()
        if venv is not None and os.environ.get("PENLARK_TOOL_REEXEC") != "1" and Path(sys.executable).resolve() != venv.resolve():
            os.environ["PENLARK_TOOL_REEXEC"] = "1"
            os.execv(str(venv), [str(venv), *sys.argv])
        raise SystemExit("The packages this tool needs are not installed for this Python. Run `make install` once, then run the tool with `.venv/bin/python tools/<name>.py` (Windows: use WSL 2).")


ensure_project_python()
