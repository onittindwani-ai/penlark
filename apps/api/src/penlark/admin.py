"""Command line set up for a real install, using the same settings file as the app (ENV_FILE, default .env).

    python -m penlark.admin add-voice "Sam Rivera" --about "Founder of a small bookkeeping firm"
    python -m penlark.admin builtin-rules

`add-voice` does what the Add a voice form does. `builtin-rules` saves the built in banned phrases (the app does this on every start, so it is only needed to check).
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from penlark.config import Settings, load_settings
from penlark.models import Author
from sendora_core.audit import record_audit
from penlark.dbsetup import make_engine, make_factories
from sendora_core.db import Base


def _factory(settings: Settings):
    import penlark.models  # noqa: F401
    from sendora_core import models as _core  # noqa: F401

    engine = make_engine(settings.database_url)
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    factory, write_factory = make_factories(engine)
    return write_factory or factory


def add_voice(factory, name: str, about: str = "") -> str:
    from penlark import service

    name = name.strip()
    if len(name) < 2:
        raise SystemExit("Type at least two characters for the name.")
    with factory() as s:
        if any(a.strip().lower() == name.lower() for a in s.scalars(select(Author.name))):
            raise SystemExit(f"There is already a voice named {name}.")
        row = Author(slug=service.unique_author_slug(s, name), name=name, about=about.strip()[:2000])
        s.add(row)
        s.flush()
        record_audit(s, "admin command", "author.created", f"author:{row.id}", {})
        s.commit()
        return row.slug


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    ap = argparse.ArgumentParser(prog="penlark.admin", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    v = sub.add_parser("add-voice", help="Add a voice: the person or brand whose writing the drafts should sound like")
    v.add_argument("name")
    v.add_argument("--about", default="")
    sub.add_parser("builtin-rules", help="Save the built in banned phrases and patterns")
    args = ap.parse_args(argv)
    settings = settings or load_settings()
    factory = _factory(settings)
    if args.command == "add-voice":
        print(f"Added the voice {args.name.strip()} ({add_voice(factory, args.name, args.about)}). Next: add some of its writing in the app's Library.")
        return 0
    from penlark import service

    with factory() as s:
        added = service.ensure_builtin_rules(s)
        s.commit()
    print(f"Built in rules saved: {added} added.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
