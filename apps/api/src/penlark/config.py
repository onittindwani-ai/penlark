"""Penlark settings. Names only in docs, never values."""

from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from penlark import cadence
from sendora_core.settings import BaseAppSettings, Mode

DEFAULT_OWNER_EMAIL = "owner@example.test"
DEMO_ALLOW_HOST = "larkspur.example.test"  # the fictional host of the demo's tracked links; used only while demo shortcuts are on


class Settings(BaseAppSettings):
    app_name: str = "penlark"
    database_url: str = "sqlite:///./penlark.sqlite3"
    owner_email: str = DEFAULT_OWNER_EMAIL
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
    redirect_allow_hosts: str = ""  # REDIRECT_ALLOW_HOSTS: hosts a tracked link may point at, comma separated. Empty means no link works. A subdomain needs its own entry or a "*.example.com" entry.
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
    timezone: str = "UTC"  # TIMEZONE: the calendar day that "today" means for exports and the calendar, for example Europe/London or America/New_York

    @field_validator("timezone")
    @classmethod
    def _timezone_known(cls, v: str) -> str:
        try:
            ZoneInfo(v.strip())
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            raise ValueError("timezone must be a name from the IANA list, for example Europe/London or UTC") from exc
        return v.strip()

    def allow_hosts(self) -> list[str]:
        """Hosts a tracked link may point at. Empty means none, except in the offline demo, which has fictional links to one fictional host."""
        hosts = [h.strip() for h in self.redirect_allow_hosts.split(",") if h.strip()]
        return hosts or ([DEMO_ALLOW_HOST] if self.demo_shortcuts else [])

    def identity_problems(self) -> list[str]:
        """What is still a placeholder. A real install sends nothing until the owner is a real address."""
        out: list[str] = []
        if self.owner_email.strip().lower() == DEFAULT_OWNER_EMAIL:
            out.append("OWNER_EMAIL is still the example address. Set the address the owner signs in with.")
        return out

    def runtime_errors(self) -> list[str]:
        out = super().runtime_errors()
        if self.mode is Mode.LIVE and not self.demo_mode:
            out += self.identity_problems()
        return list(dict.fromkeys(out))

    def problems(self) -> list[str]:
        out = [p for p in super().problems() if not (self.demo_mode and p.startswith("MODE is live while DEMO_MODE"))]
        if not self.demo_mode and not self.owner_password_hash:
            out.append("OWNER_PASSWORD_HASH is empty. Create one with tools/hash_password.py and set it before you run outside demo mode.")
        if self.demo_mode and self.owner_password_hash:
            out.append("DEMO_MODE is true but an owner password is set. The public demo password and the demo buttons are switched off; set DEMO_MODE=false for a real install.")
        if not self.demo_mode:
            out += [p for p in self.identity_problems() if p not in out]
            if not self.allow_hosts():
                out.append("REDIRECT_ALLOW_HOSTS is empty, so no tracked link can be made or followed. Set the hosts your links may point at.")
            if self.public_base_url.startswith(("http://localhost", "http://127.0.0.1")):
                out.append("PUBLIC_BASE_URL still points at this computer, so tracked links shown in the app would not open for anyone else.")
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
