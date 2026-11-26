"""Round 2: a scheduling tool on a private address is possible on purpose, and the address is looked up when it is used, not when the app starts."""

from __future__ import annotations

import socket
from datetime import datetime, timezone

import httpx
import pytest

from penlark.adapters import base
from penlark.adapters.schedulers import Buffer, Metricool, Postiz
from penlark.config import Settings
from penlark.context import Ctx
from sendora_core.adapters import AdapterError
from sendora_core.settings import Mode

WHEN = datetime(2026, 12, 2, 9, 0, tzinfo=timezone.utc)


def live(**kw):
    return Settings(mode=Mode.LIVE, demo_mode=False, session_secret="test-only-" + "x" * 30, _env_file=None, **kw)


def _addr(ip: str):
    return lambda host, port, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


def _no_dns(*a, **k):
    raise socket.gaierror("temporary failure in name resolution")


def test_the_adapters_are_built_without_any_dns_lookup(monkeypatch, tmp_path):
    monkeypatch.setattr(socket, "getaddrinfo", _no_dns)
    st = live(postiz_api_key="k", postiz_base_url="https://postiz.example.org/public/v1", scheduler_adapter="postiz", export_dir=str(tmp_path))
    Postiz(st)
    Buffer(live(buffer_token="t", buffer_base_url="https://buf.example.org"))
    Metricool(live(metricool_token="t", metricool_user_id="1", metricool_blog_id="2", metricool_base_url="https://mc.example.org/api"))
    Ctx(st, factory=None)  # the whole context, as the API and the worker build it at start up


def test_a_dns_failure_at_call_time_is_a_clear_not_sent_and_the_health_check_says_so(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _no_dns)
    p = Postiz(live(postiz_api_key="k", postiz_base_url="https://postiz.example.org/public/v1"))
    ok, detail = p.healthcheck()
    assert ok is False and "could not be found" in detail
    with pytest.raises(AdapterError, match="could not be found"):
        p.send("x", "linkedin", WHEN, "c", approved=True, confirm=True)


def test_a_name_that_points_at_a_private_address_is_refused_when_it_is_used(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _addr("10.0.0.5"))
    p = Postiz(live(postiz_api_key="k", postiz_base_url="https://postiz.example.org/public/v1"))
    with pytest.raises(AdapterError, match="private or local"):
        p.send("x", "linkedin", WHEN, "c", approved=True, confirm=True)
    assert "private or local" in p.healthcheck()[1]


def test_a_public_address_goes_through(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _addr("93.184.216.34"))
    seen = []
    client = base.guarded_client("https://postiz.example.org/public/v1", transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json=[])))
    assert client.get("/integrations").status_code == 200 and len(seen) == 1


def test_the_plain_http_private_address_needs_the_explicit_setting(monkeypatch):
    for url in ("http://postiz.internal:5000/public/v1", "https://192.168.1.20/public/v1", "http://localhost:5000"):
        with pytest.raises(AdapterError, match="ALLOW_PRIVATE_SCHEDULER"):
            base.guarded_client(url)
    monkeypatch.setattr(socket, "getaddrinfo", _no_dns)  # the setting also stops the lookup, because the address is chosen on purpose
    seen = []
    client = base.guarded_client("http://192.168.1.20:5000/public/v1", allow_private=True, transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json=[])))
    assert client.get("/integrations").status_code == 200 and len(seen) == 1
    p = Postiz(live(postiz_api_key="k", postiz_base_url="http://192.168.1.20:5000/public/v1", allow_private_scheduler=True))
    assert p.client.base_url.host == "192.168.1.20"


def test_the_private_setting_is_off_by_default_and_reported_when_on():
    assert Settings(_env_file=None).allow_private_scheduler is False
    st = Settings(allow_private_scheduler=True, _env_file=None)
    assert any("ALLOW_PRIVATE_SCHEDULER" in p for p in st.problems())
    assert not any("ALLOW_PRIVATE_SCHEDULER" in p for p in Settings(_env_file=None).problems())


def test_a_spend_limit_with_a_model_that_has_no_known_price_stops_the_start():
    from sendora_core.settings import ConfigError

    st = Settings(llm_backend="anthropic", anthropic_api_key="test-only-key", llm_budget_usd=5.0, llm_model="some-other-model-9", _env_file=None)
    assert any("no known price" in e for e in st.runtime_errors())
    with pytest.raises(ConfigError, match="LLM_BUDGET_USD"):
        st.check_runtime()
    assert any("LLM_BUDGET_USD" in p for p in st.problems())
    assert not Settings(llm_backend="anthropic", anthropic_api_key="test-only-key", llm_budget_usd=5.0, _env_file=None).budget_problems()  # the default models are priced
    assert not Settings(llm_backend="anthropic", anthropic_api_key="test-only-key", llm_model="some-other-model-9", _env_file=None).budget_problems()  # no limit set
    assert not Settings(llm_backend="fixture", llm_budget_usd=5.0, llm_model="some-other-model-9", _env_file=None).budget_problems()  # nothing live is bought


@pytest.mark.parametrize("url", ["http://localhost.evil.net", "http://127.0.0.1.evil.net/v1", "http://example.org", "https://user:pw@api.anthropic.com", "ftp://api.anthropic.com"])
def test_the_model_address_is_judged_by_its_host_not_by_how_it_starts(url):
    assert Settings(anthropic_base_url=url, _env_file=None).base_url_problems()


@pytest.mark.parametrize("url", ["https://api.anthropic.com", "https://llm-proxy.example.org/v1", "http://localhost:9000", "http://127.0.0.1:9000/v1"])
def test_the_usual_model_addresses_are_accepted(url):
    assert Settings(anthropic_base_url=url, _env_file=None).base_url_problems() == []
