"""Sign in, demo shortcuts, the refusal to start on unsafe settings, and the worker and alembic reading the same settings as the API."""

import logging
from datetime import UTC, datetime

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

from conftest import DATA, make_ctx
from hardening_helpers import APPROVER, OWNER, PASSWORD, REAL_SECRET, login, real_client, real_settings
from penlark import datadir, demo, worker
from penlark.api import routes_auth
from penlark.api.app import create_app
from penlark.config import Settings
from penlark.dburl import resolve_url
from penlark.models import Author, HouseRule
from sendora_core.models import AuditEntry
from sendora_core.settings import ConfigError
from test_migrations import cfg


def demo_client(tmp_path, **kw) -> TestClient:
    return TestClient(create_app(Settings(database_url=f"sqlite:///{tmp_path / 'd.sqlite3'}", session_secret="test-secret-test-secret", seed_dir=DATA, export_dir=str(tmp_path / "e"), _env_file=None, **kw)), base_url="http://api.test")


def authors(client) -> int:
    with client.app.state.ctx.factory() as s:
        return len(list(s.scalars(select(Author))))


# ---- demo shortcuts exist only with no owner password ----

def test_an_owner_password_switches_every_demo_shortcut_off_even_when_demo_mode_stays_on(tmp_path):
    c = real_client(tmp_path, demo_mode=True, owner_email="owner@example.test", approver_email=None, approver_password_hash=None, viewer_email=None, viewer_password_hash=None)
    for email in ("approver@example.test", "viewer@example.test", "owner@example.test"):
        assert c.post("/api/auth/login", json={"email": email, "password": "demo-password-1"}).status_code == 401, email
    h = login(c, "owner@example.test")  # the real owner password still works
    for path in ("/api/demo/state", "/api/demo/reset", "/api/demo/tick", "/api/demo/advance", "/api/demo/stress-posts"):
        assert c.request("GET" if path.endswith("state") else "POST", path, headers=h, json=None if path.endswith("state") else {"hours": 1, "n": 1}).status_code == 404, path
    assert c.get("/api/auth/me", headers=h).json()["demo_mode"] is False
    assert authors(c) == 0  # the demo data was never loaded into this database
    assert any("owner password is set" in p for p in c.app.state.ctx.settings.problems())


def test_the_demo_password_and_the_made_up_accounts_work_only_while_demo_shortcuts_are_on(tmp_path):
    c = demo_client(tmp_path, demo_mode=True)
    h = {"x-session": c.post("/api/auth/login", json={"email": "approver@example.test", "password": "demo-password-1"}).json()["token"], "x-penlark": "1"}
    assert c.get("/api/auth/me", headers=h).json() == {"user": "approver@example.test", "role": "approver", "demo_mode": True}
    assert c.post("/api/auth/login", json={"email": "approver@example.test", "password": "wrong-password"}).status_code == 401


def test_a_real_install_has_no_made_up_accounts(tmp_path):
    c = real_client(tmp_path)
    assert c.post("/api/auth/login", json={"email": "approver@example.test", "password": "demo-password-1"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "viewer@example.test", "password": "demo-password-1"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": OWNER, "password": "demo-password-1"}).status_code == 401
    assert login(c, APPROVER)["x-session"]


def test_an_owner_without_a_hash_cannot_sign_in_outside_demo_mode(tmp_path):
    c = real_client(tmp_path, owner_password_hash=None)
    assert c.post("/api/auth/login", json={"email": OWNER, "password": "demo-password-1"}).status_code == 401


def test_the_demo_clock_is_not_used_once_an_owner_password_is_set(tmp_path):
    c = real_client(tmp_path, demo_mode=True, owner_email="owner@example.test")
    with c.app.state.ctx.factory() as s:
        assert abs((c.app.state.ctx.now(s) - datetime.now(UTC)).total_seconds()) < 10  # the real time, not the fixed demo date


# ---- sign in limits ----

def test_login_key_ignores_spaces_and_capitals(tmp_path):
    c = real_client(tmp_path)
    variants = [OWNER, " " + OWNER, OWNER + " ", OWNER.upper(), "\t" + OWNER, OWNER + "\n"]
    codes = [c.post("/api/auth/login", json={"email": v, "password": "wrong-password"}).status_code for v in variants]
    assert codes[:5] == [401] * 5 and codes[5] == 429  # the sixth try is refused whatever padding it uses


def test_login_accepts_a_padded_email_with_the_right_password(tmp_path):
    r = real_client(tmp_path).post("/api/auth/login", json={"email": "  " + OWNER.upper() + " ", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["user"] == OWNER


def test_login_refuses_oversize_fields(tmp_path):
    c = real_client(tmp_path)
    assert c.post("/api/auth/login", json={"email": "a" * 300 + "@x.test", "password": "x"}).status_code == 422
    assert c.post("/api/auth/login", json={"email": OWNER, "password": "x" * 2000}).status_code == 422


def test_each_address_has_its_own_wider_limit(tmp_path):
    c = real_client(tmp_path, login_burst=2)
    codes = [c.post("/api/auth/login", json={"email": f"user{i}@x.test", "password": "x"}).status_code for i in range(40)]
    assert codes[0] == 401 and 429 in codes[30:]  # a new email every time never gets a fresh set of tries


def test_guesses_spread_over_many_addresses_still_run_out(tmp_path):
    app = create_app(real_settings(tmp_path, login_burst=2))
    codes = []
    for i in range(30):
        c = TestClient(app, base_url="http://api.test", client=(f"203.0.113.{i + 1}", 50000 + i))  # a different visitor each time
        codes.append(c.post("/api/auth/login", json={"email": OWNER, "password": "wrong-password"}).status_code)
    assert codes[0] == 401 and 429 in codes[20:]
    other = TestClient(app, base_url="http://api.test", client=("198.51.100.5", 40000))
    assert other.post("/api/auth/login", json={"email": "someone@x.test", "password": "x"}).status_code == 401  # another visitor, another account: not held up


def test_an_unknown_account_costs_the_same_work_as_a_wrong_password(tmp_path, monkeypatch):
    seen = []
    real = routes_auth.verify_password_or_dummy
    monkeypatch.setattr(routes_auth, "verify_password_or_dummy", lambda pw, h: (seen.append(h is None), real(pw, h))[1])
    c = real_client(tmp_path)
    assert c.post("/api/auth/login", json={"email": "nobody@x.test", "password": "x"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": OWNER, "password": "wrong-password"}).status_code == 401
    assert seen == [True, False]  # both went through the password check; the first against a throw away hash


# ---- the refusal to start, in the right order ----

def test_an_unsafe_start_is_refused_before_the_database_file_exists(tmp_path):
    db = tmp_path / "never.sqlite3"
    with pytest.raises(ConfigError, match="SESSION_SECRET"):
        create_app(Settings(database_url=f"sqlite:///{db}", demo_mode=False, session_secret="change-me-to-a-long-random-string", _env_file=None))
    assert not db.exists()


def test_a_live_install_with_the_example_owner_address_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="OWNER_EMAIL"):
        create_app(real_settings(tmp_path, mode="live", owner_email="owner@example.test"))
    assert TestClient(create_app(real_settings(tmp_path, mode="live"))).get("/health").json()["mode"] == "live"  # a real address is fine


def test_the_refusal_happens_before_any_demo_data_is_written(tmp_path, monkeypatch):
    db = tmp_path / "d.sqlite3"
    monkeypatch.setattr(Settings, "runtime_errors", lambda self: ["boom"])
    with pytest.raises(ConfigError):
        create_app(Settings(database_url=f"sqlite:///{db}", demo_mode=True, seed_dir=DATA, _env_file=None))
    assert not db.exists()


def test_the_worker_reads_the_same_file_and_refuses_the_same_settings(tmp_path, monkeypatch):
    env = tmp_path / "pen.env"
    env.write_text(f"DATABASE_URL=sqlite:///{tmp_path / 'w.sqlite3'}\nDEMO_MODE=false\nSESSION_SECRET=change-me-to-a-long-random-string\nTIMEZONE=Europe/London\n")
    monkeypatch.setenv("ENV_FILE", str(env))
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    assert worker.load_settings().timezone == "Europe/London"
    with pytest.raises(ConfigError, match="SESSION_SECRET"):
        worker.main()


# ---- the demo reset ----

def test_the_demo_reset_is_refused_with_an_owner_password_whatever_called_it(tmp_path):
    c = make_ctx(tmp_path, demo_mode=True)
    with c.factory() as s:
        demo.reset(s, c)
    c.settings = c.settings.model_copy(update={"owner_password_hash": "x"})
    with c.factory() as s:
        with pytest.raises(PermissionError):
            demo.reset(s, c)
        assert len(list(s.scalars(select(Author)))) == 3  # nothing was erased


def test_the_demo_reset_is_refused_on_a_server_database_unless_allowed(tmp_path):
    c = make_ctx(tmp_path, demo_mode=True)
    with c.factory() as s:
        demo.reset(s, c)
    c.settings = c.settings.model_copy(update={"database_url": "postgresql+psycopg://u:p@localhost/db"})
    with c.factory() as s:
        with pytest.raises(PermissionError, match="server database"):
            demo.reset(s, c)
        assert len(list(s.scalars(select(Author)))) == 3
    c.settings = c.settings.model_copy(update={"allow_demo_server": True})
    with c.factory() as s:
        assert demo.reset(s, c)["seed"]["authors"] == 3  # allowed on purpose (the rows here are SQLite: only the URL text was changed)


def test_the_demo_reset_never_erases_the_audit_chain(tmp_path):
    c = make_ctx(tmp_path, demo_mode=True)
    with c.factory() as s:
        demo.reset(s, c)
    with c.factory() as s:
        before = {e.id for e in s.scalars(select(AuditEntry))}
        demo.reset(s, c)
    with c.factory() as s:
        after = {e.id for e in s.scalars(select(AuditEntry))}
        assert before and before <= after
        from sendora_core.audit import verify_audit_chain

        assert verify_audit_chain(s)[0] is True


def test_the_reset_route_says_so_when_the_owner_password_is_set(tmp_path):
    c = real_client(tmp_path, demo_mode=True, owner_email="owner@example.test")
    assert c.post("/api/demo/reset", headers=login(c, "owner@example.test")).status_code == 404


# ---- the data folder is found through SEED_DIR first ----

def test_the_data_folder_comes_from_seed_dir_and_a_missing_one_is_said_plainly(tmp_path, monkeypatch):
    monkeypatch.setattr(datadir, "REPO_DATA", tmp_path / "nowhere")
    assert datadir.data_dir(DATA).name == "data"
    with pytest.raises(FileNotFoundError, match="SEED_DIR"):
        datadir.data_dir(None)
    with pytest.raises(FileNotFoundError, match="seed/authors.json"):
        datadir.data_dir(str(tmp_path))
    assert datadir.data_dir_or_none(None) is None


def test_an_installed_copy_with_no_data_folder_still_starts_and_the_reset_fails_before_erasing(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(datadir, "REPO_DATA", tmp_path / "nowhere")
    monkeypatch.setattr("penlark.api.app.REPO_DATA", tmp_path / "nowhere")
    with caplog.at_level(logging.WARNING, logger="penlark.app"):
        c = TestClient(create_app(Settings(database_url=f"sqlite:///{tmp_path / 'd.sqlite3'}", session_secret="test-secret-test-secret", demo_mode=True, seed_dir="", _env_file=None)), base_url="http://api.test")
    assert c.get("/health").status_code == 200 and "demo starts empty" in caplog.text
    h = login(c, "owner@example.test", "demo-password-1")
    assert c.post("/api/demo/reset", headers=h).status_code == 503


def test_the_reset_does_not_erase_anything_when_the_data_folder_is_missing(tmp_path, monkeypatch):
    c = make_ctx(tmp_path, demo_mode=True)
    with c.factory() as s:
        demo.reset(s, c)
    c.settings = c.settings.model_copy(update={"seed_dir": str(tmp_path / "gone")})
    with c.factory() as s:
        with pytest.raises(FileNotFoundError):
            demo.reset(s, c)
        assert len(list(s.scalars(select(Author)))) == 3 and len(list(s.scalars(select(HouseRule)))) > 100


# ---- alembic reads the same settings as the app ----

def test_alembic_reads_the_same_settings_as_the_app(tmp_path, monkeypatch):
    target = tmp_path / "from-env-file.sqlite3"
    f = tmp_path / "pen.env"
    f.write_text(f"DATABASE_URL=sqlite:///{target}\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ENV_FILE", str(f))
    assert resolve_url() == f"sqlite:///{target}"
    assert resolve_url("sqlite:///override.sqlite3") == "sqlite:///override.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'from-environment.sqlite3'}")
    assert resolve_url().endswith("from-environment.sqlite3")  # a real environment variable wins over the file, as in the app


def test_alembic_upgrade_uses_the_settings_file_and_never_guesses(tmp_path, monkeypatch):
    target = tmp_path / "upgraded.sqlite3"
    f = tmp_path / "pen.env"
    f.write_text(f"DATABASE_URL=sqlite:///{target}\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ENV_FILE", str(f))
    config = cfg("")
    config.cmd_opts = type("o", (), {"x": []})()  # no -x url: the settings file decides
    command.upgrade(config, "head")
    assert "vp_draft" in inspect(create_engine(f"sqlite:///{target}")).get_table_names()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    nowhere = tmp_path / "nowhere.env"
    nowhere.write_text("APP_NAME=x\n")
    monkeypatch.setenv("ENV_FILE", str(nowhere))
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        command.upgrade(config, "head")
