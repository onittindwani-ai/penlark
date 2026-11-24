from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import make_ctx
from mock.scheduler_mocks import BufferMock, MetricoolMock, PostizMock
from penlark.adapters.base import safe_base_url
from penlark.adapters.schedulers import Buffer, FileExport, Metricool, Postiz
from penlark.config import Settings
from penlark.registry import build_registry, build_scheduler
from sendora_core.adapters import AdapterError
from sendora_core.safety import DraftModeError, KillSwitchError
from sendora_core.settings import Mode

WHEN = datetime(2026, 12, 2, 9, 0, tzinfo=timezone.utc)


def live(**kw):
    return Settings(mode=Mode.LIVE, demo_mode=False, session_secret="x" * 20, _env_file=None, **kw)


def client(mock, base):
    return TestClient(mock.app, base_url=base)


def test_postiz_sends_the_documented_body_only_when_live_approved_and_confirmed():
    m = PostizMock()
    p = Postiz(live(postiz_api_key=m.key), client(m, "http://testserver/public/v1"))
    res = p.send("Hello", "linkedin", WHEN, "ch-1", approved=True, confirm=True)
    body = m.posts[0]
    assert res["external_id"] == "pz-1" and body["type"] == "schedule" and body["date"].endswith("Z") and body["posts"][0]["settings"]["__type"] == "linkedin"
    assert body["posts"][0]["value"][0]["content"] == "Hello"


@pytest.mark.parametrize("cls,mock,key,base", [(Postiz, PostizMock(), "postiz_api_key", "http://testserver/public/v1"), (Buffer, BufferMock(), "buffer_token", "http://testserver")])
def test_nothing_is_sent_without_approval_confirm_or_live_mode(cls, mock, key, base):
    st = live(**{key: mock.key if hasattr(mock, "key") else mock.token})
    a = cls(st, client(mock, base))
    with pytest.raises(AdapterError, match="approved"):
        a.send("x", "linkedin", WHEN, "c", approved=False, confirm=True)
    with pytest.raises(AdapterError, match="confirm"):
        a.send("x", "linkedin", WHEN, "c", approved=True, confirm=False)
    draft_mode = st.model_copy(update={"mode": Mode.DRAFT})
    a.s = draft_mode
    with pytest.raises(DraftModeError):
        a.send("x", "linkedin", WHEN, "c", approved=True, confirm=True)
    a.s = st.model_copy(update={"kill_switch": True})
    with pytest.raises(KillSwitchError):
        a.send("x", "linkedin", WHEN, "c", approved=True, confirm=True)
    assert getattr(mock, "posts") == []  # not one request reached the server


def test_buffer_saves_a_draft_by_default_and_reports_errors():
    m = BufferMock()
    b = Buffer(live(buffer_token=m.token), client(m, "http://testserver"))
    r = b.send("Draft text", "linkedin", WHEN, "chan-1", approved=True, confirm=True)
    assert m.posts[0]["saveToDraft"] is True and m.posts[0]["mode"] == "addToQueue" and "draft" in r["detail"].lower()
    with pytest.raises(AdapterError, match="channelId"):
        b.send("x", "linkedin", WHEN, "", approved=True, confirm=True)


def test_metricool_and_health_checks_and_wrong_keys():
    m = MetricoolMock()
    mc = Metricool(live(metricool_token=m.token, metricool_user_id="1", metricool_blog_id="2"), client(m, "http://testserver"))
    assert mc.send("Hi", "linkedin", WHEN, approved=True, confirm=True)["external_id"] == "mc-1" and mc.healthcheck()[0]
    bad = Metricool(live(metricool_token="wrong", metricool_user_id="1", metricool_blog_id="2"), client(m, "http://testserver"))
    assert bad.healthcheck() == (False, "Metricool refused the token.")
    pm = PostizMock()
    assert Postiz(live(postiz_api_key="nope"), client(pm, "http://testserver/public/v1")).healthcheck()[0] is False
    with pytest.raises(AdapterError):
        Postiz(live(), None)


def test_file_export_writes_a_file_and_never_sends(tmp_path):
    e = FileExport(Settings(export_dir=str(tmp_path / "out"), _env_file=None))
    r = e.export(7, "My title!", "linkedin", "Body text")
    assert (tmp_path / "out" / r["external_id"]).read_text().strip() == "Body text"
    with pytest.raises(AdapterError):
        e.send()
    assert e.healthcheck()[0]


def test_base_url_guard_refuses_private_addresses_and_credentials():
    for bad in ("https://127.0.0.1/x", "http://api.example.com", "https://user:pw@example.com", "ftp://x.com", "https://localhost"):
        with pytest.raises(AdapterError):
            safe_base_url(bad)


def test_demo_mode_only_builds_offline_adapters_and_every_adapter_is_unverified():
    with pytest.raises(AdapterError):
        build_scheduler(Settings(scheduler_adapter="postiz", postiz_api_key="k", demo_mode=True, _env_file=None))
    reg = build_registry(Settings(_env_file=None)).describe()
    assert {r["name"] for r in reg} == {"seed", "export", "postiz", "buffer", "metricool"} and not any(r["live_verified"] for r in reg)


def test_settings_problems_name_the_missing_variable():
    s = Settings(scheduler_adapter="buffer", demo_mode=False, mode=Mode.DRAFT, _env_file=None)
    probs = " ".join(s.problems())
    assert "BUFFER_TOKEN" in probs and "OWNER_PASSWORD_HASH" in probs and "LEAD_WEBHOOK_SECRET" in probs
