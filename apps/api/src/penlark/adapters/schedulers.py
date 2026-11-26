"""Scheduling adapters: file export (default), Postiz, Buffer, Metricool.

Nothing here publishes by itself. `send` needs `confirm=True`, live mode (guard_write), and a draft that a person approved (checked by the caller and again here through `approved`).
The three vendor adapters are tier B: written from public docs and tested against local imitations in mock/, never run against the real service (UNVERIFIED live).
Postiz request shape and Buffer createPost mutation were read from their docs on 2026-11-23. The Metricool shape is from memory and UNVERIFIED.
Platform APIs (LinkedIn, X, Instagram and others) need their own app approvals from each platform: the scheduler tools hold those approvals, not Penlark.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import httpx

from penlark.adapters.base import guarded_client
from sendora_core.adapters import AdapterError
from sendora_core.safety import guard_write


class UnclearAnswer(ValueError):
    """The tool answered with a success status but not with the id of a post. The post may or may not exist, so a person decides (the draft is held as "send_unknown")."""


def _post_id(value) -> str:
    """The id of a post as the tool gave it: a text or a number, never empty, never longer than the column that keeps it."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    return str(value).strip()[:120]


def _said(body) -> str:
    """What a tool said instead of an id, short and with no control characters, for the record and for the person who checks the tool."""
    found = ""
    if isinstance(body, dict):
        for key in ("message", "error", "errors", "detail"):
            v = body.get(key)
            if isinstance(v, list) and v:
                v = v[0].get("message") if isinstance(v[0], dict) else v[0]
            if isinstance(v, dict):
                v = v.get("message")
            if isinstance(v, str) and v.strip():
                found = v
                break
    return "".join(ch for ch in found if ch.isprintable())[:160]


def _no_id(tool: str, status: int, body) -> UnclearAnswer:
    said = _said(body)
    return UnclearAnswer(f"{tool} answered {status} but did not give the id of a post" + (f" and said: {said}" if said else "") + ".")


def _check(settings, approved: bool, confirm: bool, action: str) -> None:
    if not approved:
        raise AdapterError("Only an approved draft can be sent. Ask a second person to approve it first.")
    if not confirm:
        raise AdapterError("Sending needs an explicit confirm. Nothing was sent.")
    guard_write(settings, action)  # live mode only, and the kill switch wins


class FileExport:
    """The default. Writes the text to a file you copy from. Allowed in draft mode because nothing leaves your machine."""

    name = "export"

    def __init__(self, settings):
        self.dir = Path(settings.export_dir)

    def export(self, draft_id: int, title: str, platform: str, text: str) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "draft"
        path = self.dir / f"draft-{draft_id}-{platform}-{stem}.txt"
        path.write_text(text + "\n", encoding="utf-8")
        return {"external_id": path.name, "detail": f"Saved to {path.name}. Copy it and post it yourself."}

    def send(self, *a, **k):
        raise AdapterError("The file export never sends. Choose Postiz, Buffer or Metricool to schedule, and keep the mode in draft until you are ready.")

    def healthcheck(self):
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            return True, f"Export folder {self.dir.name} is writable."
        except OSError:
            return False, "The export folder is not writable."


class SeedScheduler(FileExport):
    name = "seed"

    def export(self, draft_id, title, platform, text):
        return {"external_id": f"seed-{draft_id}", "detail": "Offline demo: kept in the app only."}


class Postiz:
    name = "postiz"

    def __init__(self, settings, client: httpx.Client | None = None):
        if not settings.postiz_api_key:
            raise AdapterError("POSTIZ_API_KEY is empty.")
        self.s = settings
        self.client = client or guarded_client(settings.postiz_base_url, allow_private=getattr(settings, "allow_private_scheduler", False))

    def _h(self):
        return {"Authorization": self.s.postiz_api_key, "Content-Type": "application/json"}  # the key goes in the header with no Bearer prefix

    def export(self, draft_id, title, platform, text):
        return FileExport(self.s).export(draft_id, title, platform, text)

    def send(self, text: str, platform: str, run_at: datetime, channel_id: str, *, approved: bool, confirm: bool, as_draft: bool = False) -> dict:
        _check(self.s, approved, confirm, "postiz.create_post")
        body = {"type": "draft" if as_draft else "schedule", "date": run_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "shortLink": False, "tags": [],
                "posts": [{"integration": {"id": channel_id}, "value": [{"content": text, "image": []}], "settings": {"__type": platform}}]}
        r = self.client.post("/posts", json=body, headers=self._h())
        if r.status_code in (401, 403):
            raise AdapterError("Postiz refused the API key.")
        if r.status_code == 429:
            raise AdapterError("Postiz rate limit reached (the docs say 90 requests an hour on a self hosted default). Try later.")
        r.raise_for_status()
        data = r.json()
        first = data[0] if isinstance(data, list) and data else data
        pid = _post_id(first.get("postId") or first.get("id")) if isinstance(first, dict) else ""
        if not pid:  # a 200 with an error body or an empty list is not a post: a person looks in Postiz and says what happened
            raise _no_id("Postiz", r.status_code, first if isinstance(first, dict) else data)
        return {"external_id": pid, "detail": "Scheduled in Postiz."}

    def healthcheck(self):
        try:
            r = self.client.get("/integrations", headers=self._h())
            return (True, "Connected.") if r.status_code == 200 else (False, "Postiz refused the key." if r.status_code in (401, 403) else f"Postiz answered {r.status_code}.")
        except (httpx.HTTPError, AdapterError) as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else "Could not reach Postiz."


class Buffer:
    name = "buffer"
    MUTATION = "mutation CreatePost($input: CreatePostInput!) { createPost(input: $input) { ... on PostActionSuccess { post { id text } } ... on MutationError { message } } }"

    def __init__(self, settings, client: httpx.Client | None = None):
        if not settings.buffer_token:
            raise AdapterError("BUFFER_TOKEN is empty.")
        self.s = settings
        self.client = client or guarded_client(settings.buffer_base_url, allow_private=getattr(settings, "allow_private_scheduler", False))

    def _h(self):
        return {"Authorization": f"Bearer {self.s.buffer_token}", "Content-Type": "application/json"}

    def export(self, draft_id, title, platform, text):
        return FileExport(self.s).export(draft_id, title, platform, text)

    def send(self, text: str, platform: str, run_at: datetime, channel_id: str, *, approved: bool, confirm: bool, as_draft: bool = True) -> dict:
        _check(self.s, approved, confirm, "buffer.create_post")
        inp = {"text": text, "channelId": channel_id, "schedulingType": "automatic", "mode": "addToQueue", "saveToDraft": bool(as_draft)}
        r = self.client.post("/", json={"query": self.MUTATION, "variables": {"input": inp}}, headers=self._h())
        if r.status_code in (401, 403):
            raise AdapterError("Buffer refused the token.")
        r.raise_for_status()
        body = r.json()
        data = body.get("data") if isinstance(body, dict) else None
        res = (data.get("createPost") if isinstance(data, dict) else None) or {}
        if isinstance(res, dict) and "message" in res:
            raise AdapterError("Buffer said: " + str(res["message"])[:200])
        post = res.get("post") if isinstance(res, dict) else None
        pid = _post_id(post.get("id")) if isinstance(post, dict) else ""
        if not pid:  # GraphQL answers 200 even with an `errors` list and no post
            raise _no_id("Buffer", r.status_code, body)
        return {"external_id": pid, "detail": "Saved as a draft in Buffer." if as_draft else "Added to the Buffer queue."}

    def healthcheck(self):
        try:
            r = self.client.post("/", json={"query": "{ __typename }"}, headers=self._h())
            return (True, "Connected.") if r.status_code == 200 else (False, "Buffer refused the token." if r.status_code in (401, 403) else f"Buffer answered {r.status_code}.")
        except (httpx.HTTPError, AdapterError) as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else "Could not reach Buffer."


class Metricool:
    name = "metricool"

    def __init__(self, settings, client: httpx.Client | None = None):
        if not (settings.metricool_token and settings.metricool_user_id and settings.metricool_blog_id):
            raise AdapterError("METRICOOL_TOKEN, METRICOOL_USER_ID and METRICOOL_BLOG_ID must all be set.")
        self.s = settings
        self.client = client or guarded_client(settings.metricool_base_url, allow_private=getattr(settings, "allow_private_scheduler", False))

    def _p(self):
        return {"userId": self.s.metricool_user_id, "blogId": self.s.metricool_blog_id}

    def export(self, draft_id, title, platform, text):
        return FileExport(self.s).export(draft_id, title, platform, text)

    def send(self, text: str, platform: str, run_at: datetime, channel_id: str = "", *, approved: bool, confirm: bool, as_draft: bool = False) -> dict:
        _check(self.s, approved, confirm, "metricool.create_post")
        body = {"text": text, "providers": [{"network": platform}], "publicationDate": {"dateTime": run_at.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": "UTC"}, "draft": as_draft}
        r = self.client.post("/v2/scheduler/posts", params=self._p(), json=body, headers={"X-Mc-Auth": self.s.metricool_token})
        if r.status_code in (401, 403):
            raise AdapterError("Metricool refused the token.")
        r.raise_for_status()
        d = r.json()
        inner = (d.get("data") or d) if isinstance(d, dict) else {}
        pid = _post_id(inner.get("id")) if isinstance(inner, dict) else ""
        if not pid:
            raise _no_id("Metricool", r.status_code, d)
        return {"external_id": pid, "detail": "Scheduled in Metricool."}

    def healthcheck(self):
        try:
            r = self.client.get("/admin/simpleProfiles", params=self._p(), headers={"X-Mc-Auth": self.s.metricool_token})
            return (True, "Connected.") if r.status_code == 200 else (False, "Metricool refused the token." if r.status_code in (401, 403) else f"Metricool answered {r.status_code}.")
        except (httpx.HTTPError, AdapterError) as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else "Could not reach Metricool."
