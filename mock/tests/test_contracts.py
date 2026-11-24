"""Contract tests: the scheduler adapters against excerpts saved in mock/contracts/ (each SOURCE.txt says what was read, when, and what could not be fetched).

Only Postiz had a published OpenAPI description we could read (embedded in its docs page). Metricool's spec is public but only its start was read (auth header and base URL).
Buffer had no machine readable schema we could fetch. Nothing here ran against a real service.
"""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

from penlark.adapters.schedulers import Buffer, Metricool, Postiz
from sendora_core.settings import Mode

C = Path(__file__).resolve().parents[1] / "contracts"


def load(vendor, name):
    return json.loads((C / vendor / name).read_text(encoding="utf-8"))


def live(**kw):
    base = dict(mode=Mode.LIVE, kill_switch=False, postiz_api_key="pz-key", postiz_base_url="https://api.postiz.com/public/v1", buffer_token="bt", buffer_base_url="https://api.buffer.com",
                metricool_token="mt", metricool_user_id="1", metricool_blog_id="2", metricool_base_url="https://app.metricool.com/api", export_dir="/nonexistent-never-written")
    base.update(kw)
    return SimpleNamespace(**base)


def test_every_contract_folder_says_where_it_came_from_and_when():
    for d in C.iterdir():
        assert d.is_dir() and "2026-11-23" in (d / "SOURCE.txt").read_text(encoding="utf-8") and "https://" in (d / "SOURCE.txt").read_text(encoding="utf-8")


def post_to_postiz(**kw):
    seen = {}

    def handler(req):
        seen.update(m=req.method, p=req.url.path, h=req.headers, b=json.loads(req.content))
        return httpx.Response(200, json=load("postiz", "create_post.json")["example_response"])

    a = Postiz(live(), httpx.Client(base_url="https://api.postiz.com/public/v1", transport=httpx.MockTransport(handler)))
    out = a.send("Hello there", "linkedin", datetime(2026, 12, 14, 10, 0), "int-1", approved=True, confirm=True, **kw)
    return out, seen


def test_postiz_request_keeps_to_the_published_create_post_description():
    doc = load("postiz", "create_post.json")
    out, seen = post_to_postiz()
    assert seen["m"] == doc["method"] and seen["p"].endswith(doc["path"]) and seen["h"]["authorization"] == "pz-key" and not seen["h"]["authorization"].lower().startswith("bearer")
    b = seen["b"]
    assert set(doc["body_required"]) <= set(b) and set(b) <= set(doc["body_required"]) | set(doc["body_optional"]) | set(doc["body_required_unless_draft"])
    assert b["type"] in doc["type_values"] and isinstance(b["shortLink"], bool) and isinstance(b["tags"], list) and b["date"].endswith("Z")
    item = b["posts"][0]
    assert set(doc["post_item_required"]) <= set(item) and set(item) <= set(doc["post_item_required"]) | set(doc["post_item_optional"])
    assert set(doc["integration_required"]) <= set(item["integration"]) and set(doc["value_item_required"]) <= set(item["value"][0]) and set(item["value"][0]) <= set(doc["value_item_required"]) | set(doc["value_item_optional"])
    assert set(doc["settings_required"]) <= set(item["settings"])
    assert out["external_id"] == doc["example_response"][0]["postId"]


def test_postiz_draft_type_is_one_of_the_published_values():
    _, seen = post_to_postiz(as_draft=True)
    assert seen["b"]["type"] == "draft" and seen["b"]["type"] in load("postiz", "create_post.json")["type_values"]


def test_metricool_uses_the_published_base_url_and_auth_header():
    doc, seen = load("metricool", "auth.json"), {}

    def handler(req):
        seen.update(h=req.headers, u=str(req.url))
        return httpx.Response(200, json=[])

    Metricool(live(), httpx.Client(base_url=doc["base_url"], transport=httpx.MockTransport(handler))).healthcheck()
    assert seen["h"][doc["auth_header"].lower()] == "mt" and seen["u"].startswith(doc["base_url"]) and Metricool(live()).s.metricool_base_url == doc["base_url"]


def test_buffer_sends_a_bearer_token_to_the_documented_host():
    seen = {}

    def handler(req):
        seen.update(h=req.headers, u=str(req.url))
        return httpx.Response(200, json={"data": {"__typename": "Query"}})

    Buffer(live(), httpx.Client(base_url="https://api.buffer.com", transport=httpx.MockTransport(handler))).healthcheck()
    assert seen["h"]["authorization"] == "Bearer bt" and seen["u"].startswith("https://api.buffer.com")
