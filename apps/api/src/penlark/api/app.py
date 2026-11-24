"""The Penlark API. Every route under /api needs a signed in session, except sign in, the tracked link redirect and the signed lead webhook."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from penlark.api import routes_admin, routes_auth, routes_demo, routes_public, routes_read, routes_write
from penlark.config import Settings
from penlark.context import Ctx
from sendora_core.app import SESSION_COOKIE, create_base_app
from sendora_core.auth import read_session_token
from sendora_core.db import Base, make_engine, make_session_factory
from sendora_core.ratelimit import TokenBucket

PUBLIC = {"/api/auth/login", "/api/auth/logout", "/api/webhooks/lead"}
PUBLIC_PREFIX = ("/api/public/",)


def _seed_if_empty(ctx: Ctx) -> None:
    from sqlalchemy import select

    from penlark import demo
    from penlark.models import Author

    with ctx.factory() as s:
        if s.scalars(select(Author).limit(1)).first() is None:
            demo.reset(s, ctx)


def create_app(settings: Settings | None = None, ctx: Ctx | None = None) -> FastAPI:
    settings = settings or Settings()
    if ctx is None:
        engine = make_engine(settings.database_url)
        from sendora_core import models as _c  # noqa: F401
        import penlark.models  # noqa: F401

        if settings.database_url.startswith("sqlite"):
            Base.metadata.create_all(engine)  # SQLite zero setup path. Postgres uses `alembic upgrade head`.
        ctx = Ctx(settings, make_session_factory(engine))
        if not settings.seed_dir and (Path(__file__).resolve().parents[5] / "data").exists():
            ctx.settings.seed_dir = str(Path(__file__).resolve().parents[5] / "data")
    if ctx.settings.demo_mode:
        _seed_if_empty(ctx)
    app = create_base_app(ctx.settings, ctx.factory)
    app.title, app.version = "Penlark API", "1.0.0"
    app.state.ctx = ctx
    app.state.limiter = TokenBucket(capacity=600, refill_per_sec=20.0)
    # Sign in attempts per address and email: a burst of LOGIN_BURST (default 5), then one more every 12 seconds.
    app.state.login_bucket = TokenBucket(capacity=ctx.settings.login_burst, refill_per_sec=1 / 12)
    app.state.click_bucket = TokenBucket(capacity=60, refill_per_sec=2.0)

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        p = request.url.path
        if p.startswith("/api/") and p not in PUBLIC and not p.startswith(PUBLIC_PREFIX):
            token = request.cookies.get(SESSION_COOKIE) or request.headers.get("x-session")
            data = read_session_token(ctx.settings.session_secret, token) if token else None
            if data is None:
                return JSONResponse({"error": {"code": "http_401", "message": "Sign in to continue."}}, 401)
            request.state.user = data
        return await call_next(request)

    for r in (routes_auth, routes_read, routes_write, routes_admin, routes_public, routes_demo):
        app.include_router(r.router)
    return app


def app_from_env() -> FastAPI:  # uvicorn penlark.api.app:app_from_env --factory
    return create_app(Settings(_env_file=os.environ.get("ENV_FILE", ".env")))
