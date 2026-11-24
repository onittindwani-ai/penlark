# Updating

1. Back up the database (doc 11).
2. Pull the new version and read `../CHANGELOG.md`.
3. `make install`, or `.venv/bin/pip install -e packages/core-py -e "apps/api[dev]"` and `pnpm install`. If your environment was made with uv, use `uv pip install --python .venv/bin/python -e packages/core-py -e "apps/api[dev]"` instead of pip.
4. Postgres: `cd apps/api && ../../.venv/bin/alembic upgrade head`. SQLite creates missing tables by itself.
5. `pnpm build`, restart the API, worker and web app.
6. Run `python3 tools/doctor.py`, open the Voice profile page, and press Test on the Integrations page.

The shared `packages/` folders are copies of a base kept in the hub. Do not edit them in this repo. A needed change goes to the hub as a new base version.
