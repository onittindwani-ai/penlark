"""Record the model answers for the seed world into data/llm_fixtures/, so the demo can replay them with LLM_BACKEND=fixture and no account.

IMPORTANT: these are NOT answers of a real model. The recording goes through the real anthropic code path (request building, schema, response parsing, the checks by code)
against a local mock server that answers with the offline stand in. So the fixtures prove the replay path and the request shape, not model quality. Replace them with a
recording from a real key (LLM_RECORD=true, LLM_BACKEND=anthropic) when you have one. Never commit recordings made from real client data.

What is recorded: building the demo world with the model path on: the three voice guides (GUIDE_WRITER=model), the draft variants of the first two ideas (DRAFT_WRITER=model) and
the idea finder (IDEA_FINDER=model). Replay with the same three settings.

Run: python tools/record_llm_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
sys.path.insert(0, str(ROOT))

from mock.anthropic_mock import StubAnthropic  # noqa: E402
from penlark import demo, service  # noqa: E402
from penlark.config import Settings  # noqa: E402
from penlark.context import Ctx  # noqa: E402
from penlark.models import Note  # noqa: E402
from penlark.offline_llm import OfflineBackend  # noqa: E402
from sendora_core import models as _core  # noqa: E402,F401
from sendora_core.db import Base, make_engine, make_session_factory  # noqa: E402
from sendora_core.llm import reset_budgets  # noqa: E402

OUT = ROOT / "data" / "llm_fixtures"
MODEL_SETTINGS = {"guide_writer": "model", "draft_writer": "model", "idea_finder": "model"}


def stand_in(body: dict) -> str:
    return OfflineBackend().complete(model=body["model"], system=body.get("system", ""), prompt=body["messages"][0]["content"], max_tokens=body["max_tokens"]).text


def replay_settings(tmp: str, fixtures: Path, **kw) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp}/rep.sqlite3", session_secret="record-secret-record-secret", seed_dir=str(ROOT / "data"), export_dir=f"{tmp}/exports", llm_backend="fixture",
                    llm_fixtures_dir=str(fixtures), anthropic_api_key=None, _env_file=None, **MODEL_SETTINGS, **kw)


def record(out: Path = OUT, work: Path | None = None) -> dict:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    if work is not None:
        Path(work).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp, StubAnthropic(stand_in) as stub:
        settings = Settings(database_url=f"sqlite:///{tmp}/rec.sqlite3", session_secret="record-secret-record-secret", seed_dir=str(ROOT / "data"), export_dir=f"{tmp}/exports", llm_backend="anthropic",
                            anthropic_api_key="stub-key-for-local-server", anthropic_base_url=stub.url, llm_record=True, llm_fixtures_dir=str(out), _env_file=None, **MODEL_SETTINGS)
        eng = make_engine(settings.database_url)
        Base.metadata.create_all(eng)
        ctx = Ctx(settings, make_session_factory(eng))
        reset_budgets()
        with ctx.factory() as s:
            info = demo.reset(s, ctx)
            from sqlalchemy import select

            service.load_ideas(s, list(s.scalars(select(Note))), ctx)
            s.commit()
    files = len(list(out.glob("*.json")))
    (out / "README.txt").write_text(
        "Recorded from a LOCAL MOCK server that answers with the offline stand in. Not answers of a real model.\n"
        "They prove the replay path and the request shape only. Replay with LLM_BACKEND=fixture LLM_FIXTURES_DIR=data/llm_fixtures GUIDE_WRITER=model DRAFT_WRITER=model IDEA_FINDER=model.\n"
        "Regenerate: python tools/record_llm_fixtures.py\n", encoding="utf-8")
    return {**info["seed"], "files": files, "requests_to_mock_server": len(stub.requests)}


if __name__ == "__main__":
    print(json.dumps(record()))
