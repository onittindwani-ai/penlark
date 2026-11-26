"""Demo mode: reset to the seed data and move the clock. Sample people, offline stand ins, nothing real is touched."""

from __future__ import annotations

from sqlalchemy.orm import Session

from penlark import clock, world
from penlark.datadir import data_dir
from sendora_core.db import Base

KEEP_TABLES = {"core_audit"}  # the audit chain is evidence: even a demo reset never erases it


def reset(session: Session, ctx) -> dict:
    """Erase the working tables and load the sample seed. Only while demo shortcuts are on (DEMO_MODE and no owner password), and on SQLite unless
    ALLOW_DEMO_SERVER is set: with a real owner password, or on a server database, this is refused here too, whatever route or tool called it."""
    st = ctx.settings
    if not st.demo_shortcuts:
        raise PermissionError("The demo reset is only available in demo mode with no owner password set.")
    if not st.database_url.startswith("sqlite") and not st.allow_demo_server:
        raise PermissionError("The demo reset erases every table, so it is refused on a server database. Set ALLOW_DEMO_SERVER=true only for a throw away trial.")
    data_dir(st.seed_dir)  # a missing data folder is a plain error BEFORE anything is erased
    session.rollback()
    session.close()
    with ctx.factory() as s:
        for table in reversed(Base.metadata.sorted_tables):  # empty the tables in place: a page that polls during a reset never meets a missing table
            if table.name not in KEEP_TABLES:
                s.execute(table.delete())
        s.flush()
        clock.set_offset(s, 0.0)
        s.flush()
        info = world.load_world(s, ctx)
        s.commit()
        return {"seed": info}
