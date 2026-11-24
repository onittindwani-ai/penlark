# Quick demo (5 minutes, no accounts)

Everything in the demo is fictional: three authors, <!--n:seed.notes-->24<!--/n--> notes, <!--n:seed.posts-->60<!--/n--> posts with numbers.

1. `make install` (needs uv or Python 3.12, and pnpm: run `corepack enable` or `npm i -g pnpm` if you do not have it), then `pnpm build`.
2. Terminal 1: `DEMO_MODE=true MODE=draft .venv/bin/python -m uvicorn penlark.api.app:app_from_env --factory --port 8000`
3. Terminal 2: `cd apps/web && API_BASE_URL=http://127.0.0.1:8000 INSECURE_COOKIES=1 pnpm exec next start -p 3000`
4. Open http://localhost:3000, sign in as `owner@example.test` with the password `demo-password-1`.

With Docker: `cp .env.example .env`, set `POSTGRES_PASSWORD` and `SESSION_SECRET`, then `docker compose up -d --build`. The compose files were not run by the author (no Docker daemon): UNVERIFIED.

## The path
1. **Studio.** Replace the text with "In today's fast-paced world it is important to note that this is a game changer." Watch the voice match ring, the bars and the red underlines. Paste "I grew sales by 300 percent" and see the amber "needs a source" flag.
2. **Ask for approval** on a clean draft. Press Approve on the Approvals page: it refuses, because the person who asked cannot approve it. (The Approvals page shows the text that would be approved. If you edit a draft that is waiting, the request is withdrawn.)
3. Sign out, sign in as `approver@example.test` and approve it.
4. **Calendar.** Drag the approved draft onto a day. Nothing is sent.
5. **Studio, Export to a file.** The text is saved for you to copy.
6. **Voice profile.** Click an axis of the radar. Overlay another sample.
7. **Performance.** The learning loop shows patterns with sample sizes and says "too few to say" for the emoji trait.
8. **Attribution.** Try a link to a host that is not on the allow list: it is refused.

The Run now and +1 day buttons in the banner re run the jobs and move the demo clock; the banner shows the demo date, and Reset the demo data is in the Cmd+K palette.
