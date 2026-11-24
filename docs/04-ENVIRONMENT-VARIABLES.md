# Environment variables

Names only here. Values go in `.env` (local), the Vercel and Railway variable pages, or the server's `.env` on Hetzner. `python3 tools/check_env.py` compares your file with `.env.example`, and `python3 tools/doctor.py` tests each setting. Neither prints a secret.

Where to put each one: **Local** `.env` in the repo root. **Vercel** the project's Environment Variables page (only the web ones). **Railway** the Variables tab of each service. **Hetzner** the `.env` next to `docker-compose.yml`.

| Name | Needed | What it does and how to get it |
|---|---|---|
| `DATABASE_URL` | yes | `sqlite:///./penlark.sqlite3` for local, or `postgresql+psycopg://user:pass@host:5432/db`. Railway: copy it from the Postgres service. Costs nothing for SQLite, a small server or plan for Postgres. Wrong value: the API stops with "database_url must start with sqlite or postgresql". |
| `SESSION_SECRET` | yes | A long random string, at least 16 characters. Make one with `python3 -c "import secrets;print(secrets.token_urlsafe(48))"`. The web app and the API must use the same one. Wrong: every request answers 401. |
| `MODE` | yes | `draft` (default) sends nothing to a scheduler. `live` allows a send that is approved and confirmed. Switch to live only after doc 09. |
| `DEMO_MODE` | yes | `true` loads the fictional demo and accepts the demo password. Set `false` for real use. |
| `KILL_SWITCH` | no | `true` stops every send. Also a button in the app. |
| `OWNER_EMAIL`, `OWNER_PASSWORD_HASH` | live | Make the hash with `python3 tools/hash_password.py` and paste the result. Wrong: sign in says the email or password is wrong. |
| `APPROVER_EMAIL`, `APPROVER_PASSWORD_HASH` | live | The second person who approves drafts. Without one, nothing can be approved because the asker cannot approve their own request. |
| `NO_DASHES`, `MAX_READING_GRADE`, `MIN_VOICE_MATCH`, `REQUIRE_SOURCES` | no | House rule settings. These are decided defaults and a starting point: dashes banned in marketing text (set `NO_DASHES=false` for a client whose style uses them), reading level grade 9 or lower (a text under 8 words is not judged on reading level), a voice match of at least 60 to go to approval, and facts need sources. Change any of them for a client. The built in banned phrase list stays on; each phrase can be turned off on the Rules page. |
| `CADENCE` | no | The posting rhythm, as `platform:count` pairs separated by commas, posts per week. Default `linkedin:2,x:2` (two posts a week on LinkedIn and two on X). Platforms: linkedin, x, instagram, facebook, threads, youtube, newsletter, email. The Calendar shows planned posts against it for the next four weeks. It is a plan and a nudge: nothing is blocked or sent because of it. Empty means no target. A wrong entry makes `python3 tools/doctor.py` print a PROBLEM line. |
| `SCHEDULER_ADAPTER` | no | `export` (default), `postiz`, `buffer` or `metricool`. `seed` is the demo. |
| `EXPORT_DIR` | no | Folder for exported drafts. |
| `POSTIZ_API_KEY`, `POSTIZ_BASE_URL` | for Postiz | In Postiz: Settings, then the public API key page (UNVERIFIED page name). Cost: Postiz is free to self host. Wrong: "Postiz refused the API key." |
| `BUFFER_TOKEN`, `BUFFER_BASE_URL` | for Buffer | Create an API key at the Buffer settings API page (the docs link to publish.buffer.com/settings/api, read 2026-11-23). Wrong: "Buffer refused the token." |
| `METRICOOL_TOKEN`, `METRICOOL_USER_ID`, `METRICOOL_BLOG_ID` | for Metricool | From your Metricool account settings (UNVERIFIED, steps not readable). Wrong: "Metricool refused the token." |
| `PUBLIC_BASE_URL` | for links | The public address of the web app, used to show short links. |
| `REDIRECT_ALLOW_HOSTS` | for links | An allow list: comma separated hosts a tracked link may point at, set by the implementer for each client (their own site and booking page). Empty means no link can be made. The demo value is a fictional host. |
| `LEAD_WEBHOOK_SECRET` | for leads | Shared secret that signs lead events (doc 03). Wrong: the webhook answers 401. |
| `ALLOW_HTTP_LOCAL_TARGETS` | no | Only for local development: allows http and local hosts as link targets. Leave false in real use. |
| `LLM_BACKEND`, `ANTHROPIC_API_KEY`, `LLM_HARD_MODEL`, `LLM_BULK_MODEL` | no | Where the draft and guide writer runs. `offline` (default) is a built in template writer, not a language model, and needs no account. `fixture` replays recorded answers from `LLM_FIXTURES_DIR`. `anthropic` calls a real model and needs a key from the Anthropic console API keys page; it has not been run against the real service (UNVERIFIED). `python3 tools/doctor.py` prints `llm_backend=` and names a missing key. |
| `GUIDE_WRITER`, `DRAFT_WRITER`, `IDEA_FINDER` | no | `rules` or `model`. With a model backend on (`fixture` or `anthropic`) the voice guide (`GUIDE_WRITER`, default `model`), the draft variants (`DRAFT_WRITER`, default `model`) and extra ideas (`IDEA_FINDER`, default `rules`) can come from the model. Code re scores every draft a model writes, a person still approves, and with `LLM_BACKEND=offline` these three change nothing. See `facts/models.md`. |
| `VIEWER_EMAIL`, `VIEWER_PASSWORD_HASH` | no | A read only sign in for someone who may look but not change anything (a client who watches the queue). It opens every page and changes nothing. Make the hash with `python3 tools/hash_password.py`. |
| `LOGIN_BURST` | no | How many sign in tries one address and email may make in a row before a short wait (one more every 12 seconds). Leave it at 5 outside tests; the browser tests raise it because every test signs in from one address. |
| `API_BASE_URL` | web host | The private address of the API, for example `http://api:8000`. Wrong: pages say the server is not reachable. |
| `INSECURE_COOKIES` | no | Set `1` only for http on localhost. Never in real use. |
| `POSTGRES_PASSWORD` | compose | The database password for `docker compose`. |

Prices are not quoted here. Read each vendor's price page on the day you decide.
