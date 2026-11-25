"""The worker process: queues the recurring jobs and runs them. Start it with `python -m penlark.worker`."""

from __future__ import annotations

import logging
import signal
import time

from penlark.config import Settings
from penlark.config import load_settings as read_settings
from penlark.context import Ctx
from penlark.jobs import make_handlers, schedule_due
from penlark.dbsetup import make_engine, make_factories, require_current_schema
from sendora_core.db import Base, session_scope
from sendora_core.jobs import Worker

log = logging.getLogger("penlark.worker")


def run_once(ctx: Ctx, worker: Worker) -> int:
    with session_scope(ctx.write_factory or ctx.factory) as s:
        schedule_due(s, ctx)
    return worker.drain(limit=50)


def load_settings() -> Settings:
    """The worker reads the same environment file as the API (ENV_FILE, default .env), so the two never run on different settings."""
    return read_settings()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    settings.check_runtime()  # same refusal as the API: an example secret, a demo on a server database, a placeholder owner on a live install
    engine = make_engine(settings.database_url)
    import penlark.models  # noqa: F401
    from sendora_core import models as _c  # noqa: F401

    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
        require_current_schema(engine)
    factory, write_factory = make_factories(engine)
    ctx = Ctx(settings, factory, write_factory=write_factory)
    worker = Worker(write_factory or factory, make_handlers(ctx))  # every job may write the audit log, so on SQLite its session takes the write lock first
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    log.info("worker started: mode=%s demo=%s", settings.mode.value, settings.demo_shortcuts)
    while not stop["now"]:
        try:
            n = run_once(ctx, worker)
            if n:
                log.info("ran %d job(s)", n)
        except Exception:  # never let one bad loop stop the worker
            log.exception("worker loop error")
        time.sleep(2)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
