# Deploy the web app on Vercel

Vercel hosts only the **web** part. The API and worker need a server that stays on (Railway, Hetzner or any host that runs Docker). **Not tested: no Vercel account was used.** `next build` was run locally and passed.

The Root Directory steps were read from https://vercel.com/docs/monorepos on 2026-11-23 (VERIFIED). The rest is UNVERIFIED.

1. Put the API online first (`07` or `08`) and note its address, such as `https://api.example.com`.
2. In Vercel choose Create New, then Project, and import your Git repository.
3. Press Edit next to Root Directory and choose `apps/web`.
4. If the build cannot find `packages/ui-kit`, look for the setting that includes source files outside the Root Directory and turn it on. UNVERIFIED: the name of that setting was not on the page we read.
5. Framework Next.js. Install command `pnpm install`. Build command `pnpm build`.
6. Set `API_BASE_URL` to your API address with no trailing slash, and `SESSION_SECRET` to the same value the API uses.
7. Do not set `INSECURE_COOKIES` or `NEXT_PUBLIC_DEMO_HINT`.
8. Deploy, open the address, sign in.
9. On the API server run uvicorn with `--proxy-headers` and `--forwarded-allow-ips` set to your proxy, so rate limits see the real visitor.

## If the build fails

Most often the shared `ui-kit` folder was not included (step 4), or `pnpm-workspace.yaml` does not list `packages/*`. See `15-TROUBLESHOOTING.md`.
