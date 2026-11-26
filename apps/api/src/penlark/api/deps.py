from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from penlark.context import Ctx
from sendora_core.auth import WRITE_ROLES


def get_ctx(request: Request) -> Ctx:
    return request.app.state.ctx


def _session(request: Request, *, writes: bool) -> Iterator[Session]:
    ctx = request.app.state.ctx
    factory = ctx.write_factory if writes and ctx.write_factory is not None else ctx.factory
    s = factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def db(request: Request) -> Iterator[Session]:
    """One session per request. Every route asks for it with `Depends(db, scope="function")`: the commit then happens before the answer is sent, so a save that fails
    (a locked database, a value that is too long) is an error the person sees, never a success message for a change that was lost.
    On SQLite a request that can write takes the write lock when it starts, so two writers cannot both read the same last audit row and fork the chain."""
    yield from _session(request, writes=request.method not in SAFE_METHODS)


def db_read(request: Request) -> Iterator[Session]:
    """For a POST that only reads (a live check of a text): it never takes the write lock, so it cannot make a real save wait."""
    yield from _session(request, writes=False)


def db_write(request: Request) -> Iterator[Session]:
    """For the one GET route that writes (a click on a tracked link)."""
    yield from _session(request, writes=True)


def user(request: Request) -> dict:
    u = getattr(request.state, "user", None)
    if not u:
        raise HTTPException(401, "Sign in to continue.")
    return u


def writer(request: Request) -> dict:
    """Owner and approver can write and edit. The viewer role is read only. Deciding an approval has its own extra rule in the base."""
    u = user(request)
    if u["role"] not in WRITE_ROLES:
        raise HTTPException(403, "This sign in can look but not change anything.")
    return u


def owner(request: Request) -> dict:
    u = user(request)
    if u["role"] != "owner":
        raise HTTPException(403, "Only the owner can do this.")
    return u


def demo_only(request: Request) -> None:
    """The demo routes (clock, reset, stress) exist only while demo shortcuts are on: DEMO_MODE and no owner password hash."""
    if not request.app.state.ctx.settings.demo_shortcuts:
        raise HTTPException(404, "Not found.")
