# Run locally

1. Python 3.12 (or uv, which fetches it) and pnpm 12 (`corepack enable` or `npm i -g pnpm`). `make install` picks uv or python3.12 for you. Node 22 LTS is the supported version (`.nvmrc`).
2. `make install`
3. API: `make api`. Worker (optional): `make worker`. Web: `pnpm build` then `make web`.
4. Tests: `make test` (Python) and `pnpm e2e` (browser, needs Google Chrome).
5. `make seed-check` re runs the three evaluations. `make check-env` checks your `.env`.

The browser tests build their own demo database in `.demo/`. Delete `.demo`, `.next`, `node_modules` and `.venv` any time: they are rebuilt.
