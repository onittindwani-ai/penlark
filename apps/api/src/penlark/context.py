"""Runtime context shared by the API and the worker: settings, database, scheduler adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from penlark import clock
from penlark.config import Settings
from penlark.models import State
from penlark.offline_llm import OfflineBackend
from penlark.registry import build_registry, build_scheduler
from sendora_core.costs import CostTracker
from sendora_core.db import session_scope
from sendora_core.llm import LLM, build_llm
from sendora_core.settings import LLMBackendKind, Mode


class DetachedCosts(CostTracker):
    """Counts the cost of a model call in its own short sessions. The call itself is then free of the caller's session, so the caller can let go of the database write lock
    while the model answers (a call can take two minutes, and on SQLite one writer at a time is all there is)."""

    def __init__(self, factory: sessionmaker[Session], prices: dict | None = None):
        super().__init__(None, prices)  # type: ignore[arg-type]
        self.factory = factory

    def record(self, model: str, purpose: str, input_tokens: int, output_tokens: int):
        with session_scope(self.factory) as s:
            return CostTracker(s, self.prices).record(model, purpose, input_tokens, output_tokens)

    def total_usd(self) -> float:
        with self.factory() as s:
            return CostTracker(s, self.prices).total_usd()

    def by_purpose(self) -> dict[str, float]:
        with self.factory() as s:
            return CostTracker(s, self.prices).by_purpose()


@dataclass
class Ctx:
    settings: Settings
    factory: sessionmaker[Session]
    scheduler: Any = None
    registry: Any = None
    write_factory: Any = None  # sessions for requests that can write: on SQLite they take the write lock first (see dbsetup.py). None means the plain factory is used.

    def __post_init__(self) -> None:
        self.registry = self.registry or build_registry(self.settings)
        if self.scheduler is None:
            self.scheduler = build_scheduler(self.settings, self.registry)

    def effective(self, session: Session) -> Settings:
        """The kill switch can be turned on in the app and the mode pulled back to draft. Neither can go the other way."""
        kill, force = session.get(State, "kill_switch"), session.get(State, "force_draft")
        upd: dict[str, Any] = {}
        if kill and kill.value == "1":
            upd["kill_switch"] = True
        if force and force.value == "1":
            upd["mode"] = Mode.DRAFT
        return self.settings.model_copy(update=upd) if upd else self.settings

    def llm(self, session: Session) -> LLM:
        # LLM_BACKEND=offline (default) | fixture | anthropic. The offline stand in is the zero account default.
        # The anthropic path is UNVERIFIED against the real service (see model_tasks.py and docs 14).
        return build_llm(self.effective(session), CostTracker(session), offline=OfflineBackend())

    def llm_detached(self, eff: Settings) -> LLM:
        """The model for a call made with no session open: `eff` is `effective(session)` read before the session let go of its lock, and the cost is written in its own session."""
        return build_llm(eff, DetachedCosts(self.write_factory or self.factory), offline=OfflineBackend())

    def model_on(self) -> bool:
        """True when a model backend (fixture or anthropic) is configured. With the default offline backend every job runs as plain code, exactly as before."""
        return self.settings.effective_llm_backend is not LLMBackendKind.OFFLINE

    def now(self, session: Session):
        return clock.now(session, self.settings.demo_shortcuts)

    def today(self, session: Session) -> date:
        """The calendar day in the TIMEZONE setting (UTC by default). The demo clock is fixed and has no zone."""
        return clock.today(session, self.settings.demo_shortcuts, self.settings.timezone)


def set_state(session: Session, key: str, value: str) -> None:
    row = session.get(State, key)
    if row is None:
        session.add(State(key=key, value=value))
    else:
        row.value = value


def get_state(session: Session, key: str, default: str = "") -> str:
    row = session.get(State, key)
    return row.value if row else default
