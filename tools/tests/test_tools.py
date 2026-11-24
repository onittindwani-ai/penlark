import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import score_tools  # noqa: E402


def test_scores_validate_and_cover_every_named_tool():
    d = json.loads((ROOT / "data/tool_scores.json").read_text())
    assert score_tools.validate(d) == []
    ids = {t["id"] for g in d["groups"] for t in g["tools"]}
    assert {"buffer", "metricool", "postiz", "file", "bitly", "dub", "tracked", "anthropic", "templates", "vercel", "railway", "hetzner", "postgres", "sqlite"} <= ids


def test_a_bad_score_is_rejected():
    d = json.loads((ROOT / "data/tool_scores.json").read_text())
    d["groups"][0]["tools"][0]["scores"]["fit"]["score"] = 120
    assert any("fit" in e for e in score_tools.validate(d))


def test_tools_doc_matches_the_scores():
    assert subprocess.run([sys.executable, str(ROOT / "tools/score_tools.py"), "--check"], capture_output=True).returncode == 0


def test_seed_generator_is_deterministic(tmp_path):
    before = (ROOT / "data/seed/posts.json").read_text()
    subprocess.run([sys.executable, str(ROOT / "tools/make_seed.py")], check=True, capture_output=True)
    assert (ROOT / "data/seed/posts.json").read_text() == before


def test_evals_run_and_first_runs_exist():
    for f in ("voice_first_run", "flags_first_run", "ideas_first_run"):
        assert (ROOT / f"data/eval/{f}.json").exists()
    r = subprocess.run([sys.executable, str(ROOT / "tools/eval_voice.py")], capture_output=True, text=True)
    assert r.returncode == 0 and '"top1_correct": 24' in r.stdout
    saved = json.loads((ROOT / "data/eval/voice_first_run.json").read_text())
    assert saved["top1_correct"] == 24  # a re run must agree with the saved first run
