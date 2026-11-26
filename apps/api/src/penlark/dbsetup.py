"""The database engine of the API and the worker.

SQLite (the zero setup default) starts a transaction only when the first write arrives, so two writers can both read the same last audit row, then write after it, and the
audit chain forks: the check on the Audit page then reports a tamper that never happened. Here SQLite transactions are started by SQLAlchemy instead, and a session made
by `write_factory` begins with BEGIN IMMEDIATE, which takes the write lock first. Reads (GET requests) use the plain factory and are never held up by a writer.
Postgres already serialises the audit chain with an advisory lock in the base, so nothing changes there.
"""

from __future__ import annotations

from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from sendora_core.db import Base
from sendora_core.db import make_engine as core_make_engine
from sendora_core.db import make_session_factory

IMMEDIATE = "IMMEDIATE"


def make_engine(url: str) -> Engine:
    engine = core_make_engine(url)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _manual_transactions(dbapi_conn, _):  # pragma: no cover - driver hook
            dbapi_conn.isolation_level = None  # the driver stops guessing when a transaction starts

        @event.listens_for(engine, "begin")
        def _begin(conn):  # pragma: no cover - driver hook
            conn.exec_driver_sql("BEGIN IMMEDIATE" if conn.get_execution_options().get("sqlite_begin") == IMMEDIATE else "BEGIN")

    return engine


def make_factories(engine: Engine) -> tuple[sessionmaker[Session], sessionmaker[Session] | None]:
    """(factory for reads, factory for requests that can write). The second is None away from SQLite."""
    plain = make_session_factory(engine)
    if engine.dialect.name != "sqlite":
        return plain, None
    return plain, sessionmaker(engine.execution_options(sqlite_begin=IMMEDIATE), expire_on_commit=False)


def ensure_indexes(engine: Engine) -> list[str]:
    """`create_all` builds a missing table with its indexes, but never adds an index to a table that already exists, so a SQLite file made by an earlier version would lack the newer ones.
    Each missing index is made at start. Before a unique index is made, rows that already break it are removed (the oldest of each is kept): only a repeated event can be one.
    Postgres gets the same change from `alembic upgrade head`. Returns the names of the indexes that were made."""
    from sqlalchemy import text

    insp, made = inspect(engine), []
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {i["name"] for i in insp.get_indexes(table.name)}
        for ix in sorted(table.indexes, key=lambda i: i.name or ""):
            if ix.name in have:
                continue
            if ix.unique:
                cols = ", ".join(c.name for c in ix.columns)
                with engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM {table.name} WHERE id NOT IN (SELECT MIN(id) FROM {table.name} GROUP BY {cols})"))
            ix.create(engine)
            made.append(ix.name)
    return made


def schema_problems(engine: Engine) -> list[str]:
    """Columns the code expects that the database does not have. SQLite builds missing tables by itself but never adds a column to a table that already exists, so a file made by an older version
    would fail later with an error nobody can read. Postgres is changed with `alembic upgrade head` and is not checked here."""
    insp = inspect(engine)
    out: list[str] = []
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        missing = [c.name for c in table.columns if c.name not in have]
        if missing:
            out.append(f"the table {table.name} has no column {', '.join(missing)}")
    return out


def require_current_schema(engine: Engine) -> None:
    """Stop at start with one plain message when a SQLite file is older than the code."""
    from sendora_core.settings import ConfigError

    if engine.dialect.name != "sqlite":
        return
    problems = schema_problems(engine)
    if problems:
        raise ConfigError("The database file was made by an older version of Penlark: " + "; ".join(problems[:5]) + ". The app cannot add columns to an existing SQLite file. "
                          "Keep a copy of the file, then start with a new DATABASE_URL (a new file) and re-enter or re-import what you need, or move to Postgres, whose upgrades run with `alembic upgrade head`. See docs/12-UPDATING.md.")
