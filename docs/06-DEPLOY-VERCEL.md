# Deploy the web app on Vercel

Vercel hosts only the **web** part. The API and worker need a server that stays on (Railway, Hetzner or any host that runs Docker). **Not tested: no Vercel account was used.** The web build is made by the CI workflow on every push; it was not run by hand for this release.

The Root Directory steps were read from https://vercel.com/docs/monorepos on 2026-11-23 (VERIFIED). The rest is UNVERIFIED.

1. Put the API online first (`07` or `08`) and note its address, such as `https://api.example.com`.
2. In Vercel choose Create New, then Project, and import your Git repository.
3. Press Edit next to Root Directory and choose `apps/web`.
4. If the build cannot find `packages/ui-kit`, look for the setting that includes source files outside the Root Directory and turn it on. UNVERIFIED: the name of that setting was not on the page we read.
5. Framework Next.js. Install command `pnpm install`. Build command `pnpm build`.
6. Set `API_BASE_URL` to your API address with no trailing slash. Do not put `SESSION_SECRET` on Vercel: the web app never reads it, it only passes on the session cookie the API gives out, and the signing key belongs on the API and the worker alone.
7. Do not set `INSECURE_COOKIES` or `NEXT_PUBLIC_DEMO_HINT`.
8. Deploy, open the address, sign in.
9. On the API server run uvicorn with `--proxy-headers` and set `FORWARDED_ALLOW_IPS` to the address your web app reaches the API from (the Docker image reads that variable and defaults to `127.0.0.1`; never `*`), so rate limits see the real visitor (without it every visitor shares one limit, and the settings page warns about it). The web app passes on only the last address of `X-Forwarded-For`, the one its own front end added.

## Upload size

The web app accepts an upload of up to 8 MB, but Vercel's own documentation limits the request body of a function to 4.5 MB, so a bigger file is refused by Vercel before it reaches Penlark. This limit was read, not tested here (UNVERIFIED). For larger files run the web app from its Docker image (doc 08), or split the file.

## If the build fails

Most often the shared `ui-kit` folder was not included (step 4), or `pnpm-workspace.yaml` does not list `packages/*`. See `15-TROUBLESHOOTING.md`.
