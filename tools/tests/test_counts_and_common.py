import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_docs  # noqa: E402
import measure  # noqa: E402


def test_the_counts_file_agrees_with_the_files():
    assert measure.drift(json.loads((ROOT / "data" / "counts.json").read_text())) == []


def test_a_stale_count_is_reported_by_name():
    counts = json.loads((ROOT / "data" / "counts.json").read_text())
    stale = {**counts, "api_paths": counts["api_paths"] - 1, "tables": counts["tables"] + 3}
    msgs = measure.drift(stale)
    assert len(msgs) == 2 and any("api_paths" in m for m in msgs) and any("tables" in m for m in msgs)


def test_the_check_docs_run_fails_when_a_count_drifts(tmp_path, monkeypatch):
    real = measure.cheap_counts
    monkeypatch.setattr(measure, "cheap_counts", lambda: {**real(), "pages": 99})
    assert check_docs.main([]) == 1


def test_the_openapi_file_is_the_one_the_app_writes():
    import tempfile

    from penlark.api.app import create_app
    from penlark.config import Settings

    with tempfile.TemporaryDirectory() as d:
        live = create_app(Settings(_env_file=None, database_url=f"sqlite:///{d}/x.sqlite3", export_dir=d)).openapi()
    assert live == json.loads((ROOT / "docs" / "openapi.json").read_text()), "run python tools/export_openapi.py"


def test_a_tool_started_with_no_packages_says_what_to_do_in_one_sentence():
    # -S leaves out the installed packages, as a bare python would
    p = subprocess.run([sys.executable, "-S", str(ROOT / "tools" / "doctor.py")], capture_output=True, text=True, cwd=ROOT)
    assert p.returncode != 0 and "make install" in p.stderr and "Traceback" not in p.stderr


def test_a_tool_started_with_the_system_python_finds_the_project_python():
    # whatever python3 the machine has, the tool must run (it starts again with .venv when it needs to); a machine with no .venv has nothing to prove here
    if not (ROOT / ".venv").exists():
        return
    p = subprocess.run(["python3", str(ROOT / "tools" / "doctor.py")], capture_output=True, text=True, cwd=ROOT)
    assert "ModuleNotFoundError" not in p.stderr and "mode=" in p.stdout
