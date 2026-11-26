# Facts and sources

Every outside fact, with where it came from, the date, and whether it was run for real. VERIFIED means read from the vendor's current page that day. Nothing was run against a real vendor account.

| Fact | Source | Date | Status |
|---|---|---|---|
| Postiz public API: base `https://api.postiz.com/public/v1`, key in the `Authorization` header with no Bearer, `POST /posts` with type, date, shortLink, tags, posts with integration id, value content, settings type, limit 90 an hour | https://docs.postiz.com/public-api/introduction | 2026-11-23 | VERIFIED from docs, adapter not run live |
| Postiz OpenAPI 3.1.0 (embedded in the create post page): required body fields, draft type, response a list of postId and integration | https://docs.postiz.com/public-api/posts/create | 2026-11-23 | VERIFIED from docs, contract test in `mock/tests/test_contracts.py` |
| Buffer API: GraphQL at `https://api.buffer.com`, Bearer token, `createPost` with text, channelId, schedulingType, mode, saveToDraft | https://developers.buffer.com/examples/create-draft-post.html | 2026-11-23 | VERIFIED from docs, adapter not run live |
| Buffer scheduled post example | not read | | UNVERIFIED |
| Metricool OpenAPI 3.0.1 exists at app.metricool.com/api/swagger.json; base URL and auth header X-Mc-Auth read, the scheduler post path was NOT read (file about 1.6 million characters) | https://app.metricool.com/api/swagger.json | 2026-11-23 | header and base URL VERIFIED, post shape UNVERIFIED |
| Language model path: `POST /v1/messages` through the base wrapper, three jobs, code re scoring | see `facts/models.md` | 2026-11-23 | UNVERIFIED live (mock server and fixtures only) |
| LinkedIn Shares.csv columns (Date, ShareLink, ShareCommentary, SharedUrl, MediaUrl, Visibility) | memory (help page could not be read) | 2026-11-23 | UNVERIFIED |
| X archive tweets.js layout (`window.YTD.tweets.part0 = [...]`, `tweet.full_text`) | memory | 2026-11-23 | UNVERIFIED |
| YouTube transcript text with timestamps | handled as plain text lines | 2026-11-23 | UNVERIFIED layout |
| Vercel monorepo Root Directory | https://vercel.com/docs/monorepos | 2026-11-23 | VERIFIED |
| Railway, Hetzner, Cloudflare steps | not fetched | | UNVERIFIED |
| Library versions in `apps/web/package.json` and `apps/api/pyproject.toml` | inherited from the shared base, which recorded them with a date | base 1.1.1 | see the base notes |

Per vendor notes: `facts/postiz.md`, `facts/buffer.md`, `facts/metricool.md`, `facts/exports.md`. Prices are never quoted.
