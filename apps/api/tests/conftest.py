import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps/api/src"), str(ROOT)]

from fastapi.testclient import TestClient  # noqa: E402

from penlark.api.app import create_app  # noqa: E402
from penlark.config import Settings  # noqa: E402
from penlark.context import Ctx  # noqa: E402
from sendora_core import models as _core  # noqa: E402,F401
from sendora_core.db import Base, make_engine, make_session_factory  # noqa: E402

DATA = str(ROOT / "data")


def make_ctx(tmp_path, **kw) -> Ctx:
    s = Settings(database_url=f"sqlite:///{tmp_path / 't.sqlite3'}", session_secret="test-secret-test-secret", seed_dir=DATA, export_dir=str(tmp_path / "exports"), _env_file=None, **kw)
    eng = make_engine(s.database_url)
    Base.metadata.create_all(eng)
    return Ctx(s, make_session_factory(eng))


@pytest.fixture()
def ctx(tmp_path):
    return make_ctx(tmp_path)


@pytest.fixture(scope="session")
def _world_db(tmp_path_factory):
    from penlark import demo

    c = make_ctx(tmp_path_factory.mktemp("world"))
    with c.factory() as s:
        demo.reset(s, c)
    return c


@pytest.fixture()
def ro(_world_db):
    return _world_db


@pytest.fixture()
def world(tmp_path):
    from penlark import demo

    c = make_ctx(tmp_path)
    with c.factory() as s:
        demo.reset(s, c)
    return c


@pytest.fixture()
def client(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'api.sqlite3'}", session_secret="test-secret-test-secret", seed_dir=DATA, export_dir=str(tmp_path / "exports"), lead_webhook_secret="hook-secret-for-tests", _env_file=None))
    return TestClient(app)


def login(client, email="owner@example.test"):
    r = client.post("/api/auth/login", json={"email": email, "password": "demo-password-1"})
    assert r.status_code == 200, r.text
    return {"x-session": r.json()["token"], "x-penlark": "1"}


def seed_samples(a):
    import json

    return json.loads((Path(DATA) / "seed" / f"samples_{a}.json").read_text())


@pytest.fixture(autouse=True)
def _no_key_from_the_shell(monkeypatch):
    """The developer's shell may hold a real ANTHROPIC_API_KEY. No test may use it: tests that need a key set one explicitly and point it at a local fake server."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
