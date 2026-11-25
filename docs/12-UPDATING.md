# Updating

1. Back up the database (doc 11).
2. Pull the new version and read `../CHANGELOG.md`.
3. `make install`, or `.venv/bin/pip install -c constraints.txt -e packages/core-py -e "apps/api[dev]"` and `pnpm install`. If your environment was made with uv, use `uv pip install --python .venv/bin/python -c constraints.txt -e packages/core-py -e "apps/api[dev]"` instead of pip.
4. Postgres: `cd apps/api && ../../.venv/bin/alembic upgrade head`. SQLite creates missing tables by itself, but it cannot add a column to a table that already exists. The API and the worker check for that at start and stop with one message ("made by an older version") if the file is behind the code. Then keep a copy of the file, start with a new `DATABASE_URL` (a new file) and re enter or re import what you need, or move to Postgres. Version 1.0.1 changes no table, so a 1.0.0 file keeps working.
5. `pnpm build`, restart the API, worker and web app.
6. Run `python3 tools/doctor.py`, open the Voice profile page, and press Test on the Integrations page.

The shared `packages/` folders are copies of a base kept in the hub. Do not edit them in this repo. A needed change goes to the hub as a new base version.

## Pinned packages

`constraints.txt` pins every third party Python package to the version the tests ran against, so an install today gives the same set as the one that was tested (`make install`, the Docker image and CI all use it). The file pins versions only, not file hashes: an install does not verify the downloaded files against a fixed hash (UNVERIFIED against a package index attack; pip's `--require-hashes` needs hashes the generator in the hub does not write yet). After a deliberate upgrade of a package, install the new version, run the tests, then rewrite the file with `tools/make_constraints.py` from the hub repository (`sendora-ai-systems`).
