# Run locally

1. Python 3.12 (or uv, which fetches it) and pnpm 12 (`corepack enable` or `npm i -g pnpm`). `make install` picks uv or python3.12 for you. Node 22 LTS is the supported version (`.nvmrc`). On Ubuntu or Debian also run `sudo apt install python3-venv` (the line that makes `python3 -m venv` work). On Windows use WSL 2 with Ubuntu: PowerShell and cmd are not supported.
2. `make install`
3. API: `make api`. Worker: `make worker`. Web: `pnpm build` then `make web`. The offline demo needs no worker (the Find ideas button answers at once). A real install (`DEMO_MODE=false`) needs it running: Find ideas is queued for the worker, and the hourly learning loop runs there. Safari: with `make web` the session cookie is marked Secure, and whether Safari keeps a Secure cookie on plain `http://localhost` was not tested here. If you cannot stay signed in on Safari, set `INSECURE_COOKIES=1` for local use only, or use Chrome or Firefox.
4. Tests: `make test` (Python) and `pnpm e2e` (browser, needs Google Chrome).
5. `make seed-check` re runs the three evaluations. `make check-env` checks your `.env`.
6. The scripts in `tools/` (`doctor.py`, `hash_password.py` and the others) start the project's own Python by themselves, so `python3 tools/doctor.py` works on a fresh clone once `make install` has made `.venv`. Without a `.venv` they say to run `make install`. You can always run them as `.venv/bin/python tools/doctor.py`.

## Your own install (not the demo)

`cp .env.example .env`, then follow `04-ENVIRONMENT-VARIABLES.md`. For your own install set `SESSION_SECRET` (32 or more random characters), `OWNER_EMAIL`, `OWNER_PASSWORD_HASH` and `APPROVER_EMAIL` with `APPROVER_PASSWORD_HASH`, and keep `DEMO_MODE=false`. To keep the settings somewhere else, set `ENV_FILE=/path/to/file`: the API, the worker, the database migration and the `penlark.admin` commands all read that file instead of `.env`.

A new install starts empty, with the built in banned phrases already in place. Add the first voice (the person or brand you write for) on the Studio, Library or Voice profile page with **Add a voice**, or with `python -m penlark.admin add-voice "Sam Rivera"`. Then add some of their writing in the Library and build the profile (`10`).

The browser tests build their own demo database in `.demo/`. Delete `.demo`, `.next`, `node_modules` and `.venv` any time: they are rebuilt.
