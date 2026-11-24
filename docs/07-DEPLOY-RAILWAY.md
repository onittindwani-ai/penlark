# Deploy the API and worker on Railway

**Not tested: no Railway account was used and no Docker image was built here (no Docker daemon).** `deploy/railway/railway.json` is checked only for valid syntax. The steps are UNVERIFIED, from general knowledge. Check them against https://docs.railway.com.

1. Create a project and add a **Postgres** database.
2. Add a service from your Git repository. Use `apps/api/Dockerfile` as the build file (the file `railway.json` already says so).
3. In the service Variables tab set `DATABASE_URL` from the Postgres service (use the `postgresql+psycopg://` form), `SESSION_SECRET`, `OWNER_EMAIL`, `OWNER_PASSWORD_HASH`, `APPROVER_EMAIL`, `APPROVER_PASSWORD_HASH`, `LEAD_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`, `REDIRECT_ALLOW_HOSTS`, `DEMO_MODE=false`, and `MODE=draft`.
4. Add a **volume** and mount it at `/data/exports`. Set `EXPORT_DIR=/data/exports`. Exported drafts are saved there.
5. Add a second service from the same repository for the **worker**, with the start command `python -m penlark.worker` and the same variables.
6. The lead webhook (`/api/webhooks/lead`) must be reachable from your form tool, so give the API a public address. Run the migrations once from a shell on the API service: `alembic upgrade head`.
7. Set the health check path to `/health` (already in `railway.json`).
8. Put the web app on Vercel (doc 06) or run `apps/web/Dockerfile` as a third service, with `API_BASE_URL` set to the API's internal or public address.

Cost depends on your plan. Read Railway's price page yourself, none is quoted here.
