"""Penlark settings. Names only in docs, never values."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from penlark import cadence
from sendora_core.settings import BaseAppSettings


class Settings(BaseAppSettings):
    app_name: str = "penlark"
    database_url: str = "sqlite:///./penlark.sqlite3"
    owner_email: str = "owner@example.test"
    owner_password_hash: str | None = None
    approver_email: str | None = None
    approver_password_hash: str | None = None
    viewer_email: str | None = None  # read only role: may look at everything, change nothing
    viewer_password_hash: str | None = None
    login_burst: int = Field(default=5, ge=1, le=1000)  # sign in tries in a row before a short wait; the browser tests raise it

    scheduler_adapter: str = "export"  # export, postiz, metricool, buffer, seed
    export_dir: str = "./exports"
    seed_dir: str = ""
    postiz_api_key: str = ""
    postiz_base_url: str = "https://api.postiz.com/public/v1"
    metricool_token: str = ""
    metricool_user_id: str = ""
    metricool_blog_id: str = ""
    metricool_base_url: str = "https://app.metricool.com/api"
    buffer_token: str = ""
    buffer_base_url: str = "https://api.buffer.com"
    public_base_url: str = "http://localhost:3000"  # where tracked links live, for example https://go.example.com
    redirect_allow_hosts: str = "larkspur.example.test"  # allow list of hosts a tracked link may point at; the implementer sets it for each client
    lead_webhook_secret: str = ""
    allow_http_local_targets: bool = False

    # House rule defaults. Decided defaults, a starting point the implementer changes for each client.
    no_dashes: bool = True  # dashes are banned in marketing text; set NO_DASHES=false for a client whose style uses them
    max_reading_grade: float = 9.0  # marketing text should read at grade 9 or lower
    min_voice_match: int = 60  # a draft scoring under this does not go to approval
    require_sources: bool = True
    # Which jobs a model does when a model backend is on (LLM_BACKEND=fixture or anthropic). With LLM_BACKEND=offline (the default) none of these changes anything.
    guide_writer: Literal["rules", "model"] = "model"  # GUIDE_WRITER=model writes the voice guide with the model; a person still edits and locks it
    draft_writer: Literal["rules", "model"] = "model"  # DRAFT_WRITER=model writes the variants; code re scores each one and a second person still approves
    idea_finder: Literal["rules", "model"] = "rules"  # IDEA_FINDER=model lets the model add ideas the plain finder missed; code verifies every quote
    cadence: str = "linkedin:2,x:2"  # posts a week per platform, a plan and a nudge on the calendar, never a block

    def allow_hosts(self) -> list[str]:
        return [h.strip() for h in self.redirect_allow_hosts.split(",") if h.strip()]

    def problems(self) -> list[str]:
        out = [p for p in super().problems() if not (self.demo_mode and p.startswith("MODE is live while DEMO_MODE"))]
        if not self.demo_mode and not self.owner_password_hash:
            out.append("OWNER_PASSWORD_HASH is empty. Create one with tools/hash_password.py and set it before you run outside demo mode.")
        try:
            cadence.parse(self.cadence)
        except ValueError as exc:
            out.append(str(exc))
        need = {"postiz": (self.postiz_api_key, "POSTIZ_API_KEY"), "buffer": (self.buffer_token, "BUFFER_TOKEN"), "metricool": (self.metricool_token, "METRICOOL_TOKEN")}
        if self.scheduler_adapter in need and not need[self.scheduler_adapter][0]:
            out.append(f"SCHEDULER_ADAPTER is {self.scheduler_adapter} but {need[self.scheduler_adapter][1]} is empty.")
        if not self.demo_mode and not self.lead_webhook_secret:
            out.append("LEAD_WEBHOOK_SECRET is empty. Lead events from your form tool cannot be checked until you set it.")
        return out
