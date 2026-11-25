# Deploy the API and worker on Railway

**Not tested on Railway: no Railway account was used.** The GitHub workflow builds `apps/api/Dockerfile` and starts the compose stack on a GitHub machine, but nothing was deployed to a real host. `deploy/railway/railway.json` is checked only for valid syntax. The steps are UNVERIFIED, from general knowledge. Check them against https://docs.railway.com.

1. Create a project and add a **Postgres** database.
2. Add a service from your Git repository. Use `apps/api/Dockerfile` as the build file (the file `railway.json` already says so).
3. In the service Variables tab set `DATABASE_URL` from the Postgres service (use the `postgresql+psycopg://` form), `SESSION_SECRET` (32 or more random characters: the app refuses to start on a shorter or example one), `OWNER_EMAIL`, `OWNER_PASSWORD_HASH`, `APPROVER_EMAIL`, `APPROVER_PASSWORD_HASH`, `LEAD_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`, `REDIRECT_ALLOW_HOSTS`, `TIMEZONE`, `DEMO_MODE=false`, and `MODE=draft`. The image already sets `DEMO_MODE=false`, so a service missing its variables stops at start with a list of what is wrong instead of running as a public demo. Do not skip the worker in step 5: on a real install the Find ideas button and the hourly learning loop run there. Set `FORWARDED_ALLOW_IPS` to the address your web service reaches the API from (never `*`): without it every visitor shares one rate limit, and the settings page shows a warning.
4. Add a **volume** and mount it at `/data/exports`. Set `EXPORT_DIR=/data/exports`. Exported drafts are saved there.
5. Add a second service from the same repository for the **worker**, with the start command `python -m penlark.worker` and the same variables.
6. The lead webhook (`/api/webhooks/lead`) must be reachable from your form tool, so give the API a public address. Run the migrations once from a shell on the API service: `alembic upgrade head`.
7. Set the health check path to `/health` (already in `railway.json`).
8. Put the web app on Vercel (doc 06) or run `apps/web/Dockerfile` as a third service, with `API_BASE_URL` set to the API's internal or public address.

Cost depends on your plan. Read Railway's price page yourself, none is quoted here.
