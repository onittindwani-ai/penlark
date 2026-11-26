"""Penlark settings. Names only in docs, never values."""

from __future__ import annotations

import os
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError, field_validator

from penlark import cadence
from sendora_core.costs import DEFAULT_PRICES
from sendora_core.settings import BaseAppSettings, ConfigError, LLMBackendKind, Mode

DEFAULT_OWNER_EMAIL = "owner@example.test"
DEMO_ALLOW_HOST = "larkspur.example.test"  # the sample host of the demo's tracked links; used only while demo shortcuts are on


def load_settings(env_file: str | None = None) -> "Settings":
    """Read the settings for the API, the worker and the command line tools. A value that is not accepted is reported by name only: pydantic's own message
    would print the value, and a too short SESSION_SECRET is a secret."""
    try:
        return Settings(_env_file=env_file if env_file is not None else os.environ.get("ENV_FILE", ".env"))
    except ValidationError as exc:
        found = "; ".join(f"{'.'.join(str(p).upper() for p in e['loc']) or 'settings'}: {e['msg']}" for e in exc.errors(include_input=False, include_url=False, include_context=False))
        raise ConfigError(f"The settings are not accepted. {found}") from None


class Settings(BaseAppSettings):
    app_name: str = "penlark"
    database_url: str = Field(default="sqlite:///./penlark.sqlite3", repr=False)  # a Postgres address holds the password: it never shows in the text of the settings
    owner_email: str = DEFAULT_OWNER_EMAIL
    owner_password_hash: str | None = Field(default=None, repr=False)
    approver_email: str | None = None
    approver_password_hash: str | None = Field(default=None, repr=False)
    viewer_email: str | None = None  # read only role: may look at everything, change nothing
    viewer_password_hash: str | None = Field(default=None, repr=False)
    login_burst: int = Field(default=5, ge=1, le=1000)  # sign in tries in a row before a short wait; the browser tests raise it

    scheduler_adapter: str = "export"  # export, postiz, metricool, buffer, seed
    export_dir: str = "./exports"
    seed_dir: str = ""
    postiz_api_key: str = Field(default="", repr=False)
    postiz_base_url: str = "https://api.postiz.com/public/v1"
    metricool_token: str = Field(default="", repr=False)
    metricool_user_id: str = ""
    metricool_blog_id: str = ""
    metricool_base_url: str = "https://app.metricool.com/api"
    buffer_token: str = Field(default="", repr=False)
    buffer_base_url: str = "https://api.buffer.com"
    public_base_url: str = "http://localhost:3000"  # where tracked links live, for example https://go.example.com
    redirect_allow_hosts: str = ""  # REDIRECT_ALLOW_HOSTS: hosts a tracked link may point at, comma separated. Empty means no link works. A subdomain needs its own entry or a "*.example.com" entry.
    lead_webhook_secret: str = Field(default="", repr=False)
    allow_http_local_targets: bool = False
    allow_private_scheduler: bool = False  # ALLOW_PRIVATE_SCHEDULER: the scheduling tool's address may be plain http or a private or local address, for a Postiz you run yourself. Off by default.

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

    send_hour: int = Field(default=9, ge=0, le=23)  # SEND_HOUR: the hour of the day, in TIMEZONE, at which a send for a chosen day goes out (09 means 9 in the morning)

    @field_validator("timezone")
    @classmethod
    def _timezone_known(cls, v: str) -> str:
        try:
            ZoneInfo(v.strip())
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            raise ValueError("timezone must be a name from the IANA list, for example Europe/London or UTC") from exc
        return v.strip()

    @field_validator("owner_email", "approver_email", "viewer_email")
    @classmethod
    def _email_fits_the_log(cls, v: str | None) -> str | None:
        """The audit log and the approvals keep who did it in 80 characters. A longer address would be refused by a Postgres database in the middle of a request."""
        if v is not None and len(v.strip()) > 80:
            raise ValueError("an email address here must be at most 80 characters")
        return v

    def allow_hosts(self) -> list[str]:
        """Hosts a tracked link may point at. Empty means none, except in the offline demo, which has sample links to one sample host."""
        hosts = [h.strip() for h in self.redirect_allow_hosts.split(",") if h.strip()]
        return hosts or ([DEMO_ALLOW_HOST] if self.demo_shortcuts else [])

    def identity_problems(self) -> list[str]:
        """What is still a placeholder. A real install sends nothing until the owner is a real address."""
        out: list[str] = []
        if self.owner_email.strip().lower() == DEFAULT_OWNER_EMAIL:
            out.append("OWNER_EMAIL is still the example address. Set the address the owner signs in with.")
        return out

    def budget_problems(self) -> list[str]:
        """A spend limit only works for a model with a known price: the base prices an unlisted model at nothing, so the limit would never be reached. Refuse that start."""
        if self.llm_budget_usd is None or self.effective_llm_backend is not LLMBackendKind.ANTHROPIC:
            return []
        unpriced = sorted({m for m in (self.model_for("hard"), self.model_for("bulk")) if m not in DEFAULT_PRICES})
        if not unpriced:
            return []
        return [f"LLM_BUDGET_USD is set but the model {', '.join(unpriced)} has no known price, so the spend would be counted as zero and the limit would never stop anything. Use a listed model ({', '.join(sorted(DEFAULT_PRICES))}) or leave LLM_BUDGET_USD empty and use LLM_CALL_BUDGET."]

    def base_url_problems(self) -> list[str]:
        """The base file only checks how the address starts, so `http://localhost.evil.net` passes it. The host is read here: plain http is for exactly localhost, 127.0.0.1 or ::1."""
        u = urlparse(self.anthropic_base_url)
        if u.scheme == "https" and u.hostname and not u.username and not u.password:
            return []
        if u.scheme == "http" and u.hostname in {"localhost", "127.0.0.1", "::1"} and not u.username and not u.password:
            return []
        return ["ANTHROPIC_BASE_URL must be an https:// address without a user name or password (plain http only for localhost, 127.0.0.1 or ::1 in tests). The model key is sent to this address."]

    def runtime_errors(self) -> list[str]:
        out = super().runtime_errors() + self.budget_problems() + self.base_url_problems()
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
        if self.allow_private_scheduler:
            out.append("ALLOW_PRIVATE_SCHEDULER is on: the scheduling tool's address may be plain http or point at a private network address. Keep it on only for a tool you run yourself.")
        if not self.demo_mode and not self.lead_webhook_secret:
            out.append("LEAD_WEBHOOK_SECRET is empty. Lead events from your form tool cannot be checked until you set it.")
        return out
