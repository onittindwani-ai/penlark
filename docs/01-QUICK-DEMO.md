# Quick demo (5 minutes, no accounts)

Everything in the demo is sample data: three authors, <!--n:seed.notes-->24<!--/n--> notes, <!--n:seed.posts-->60<!--/n--> posts with numbers.

1. `make install` (needs uv or Python 3.12, and pnpm: run `corepack enable` or `npm i -g pnpm` if you do not have it), then `pnpm build`.
2. Terminal 1: `DEMO_MODE=true MODE=draft .venv/bin/python -m uvicorn penlark.api.app:app_from_env --factory --port 8000`
3. Terminal 2: `cd apps/web && API_BASE_URL=http://127.0.0.1:8000 INSECURE_COOKIES=1 pnpm exec next start -p 3000`
4. Open http://localhost:3000, sign in as `owner@example.test` with the password `demo-password-1`.

The demo password, the demo `approver@example.test` and `viewer@example.test` accounts and the demo buttons exist only while `DEMO_MODE=true` and `OWNER_PASSWORD_HASH` is empty. Never put a demo on the internet with real writing in it.

Docker is for a real install, not for the demo: a demo refuses to start on the Postgres database that compose uses. For a real install with Docker: `cp .env.example .env`, keep `DEMO_MODE=false`, set a `SESSION_SECRET` of 32 or more random characters (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`), `OWNER_EMAIL`, `OWNER_PASSWORD_HASH` (from `python3 tools/hash_password.py`) and `POSTGRES_PASSWORD` (letters and digits only, for example `openssl rand -hex 24`), then `docker compose up -d --build`. The GitHub workflow in `.github/workflows/ci.yml` builds the images and starts this stack on a GitHub machine; the compose files were never run on a real server by the author.

## The path
1. **Studio.** Replace the text with "In today's fast-paced world it is important to note that this is a game changer." Watch the voice match ring, the bars and the red underlines. Paste "I grew sales by 300 percent" and see the amber "needs a source" flag.
2. **Ask for approval** on a clean draft. Press Approve on the Approvals page: it refuses, because the person who asked cannot approve it. (The Approvals page shows every character that would be approved, and an approval is for those exact words: if you edit a draft that is waiting, the request is withdrawn, and a draft changed after it was approved cannot be exported.)
3. Sign out, sign in as `approver@example.test` and approve it.
4. **Calendar.** Drag the approved draft onto a day. Nothing is sent.
5. **Studio, Export to a file.** The text is saved for you to copy.
6. **Voice profile.** Click an axis of the radar. Overlay another sample.
7. **Performance.** The learning loop shows patterns with sample sizes and says "too few to say" for the emoji trait.
8. **Attribution.** Try a link to a host that is not on the allow list: it is refused.

The Run now and +1 day buttons in the banner re run the jobs and move the demo clock; the banner shows the demo date, and Reset the demo data is in the Cmd+K palette.
