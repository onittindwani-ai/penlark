# Metricool

A public OpenAPI 3.0.1 file exists at https://app.metricool.com/api/swagger.json (read 2026-11-23: base URL `https://app.metricool.com/api`, auth header `X-Mc-Auth`); only its first 100000 of about 1.6 million characters were read, so the scheduler post path was not. The marketing page described no API. The adapter assumes `POST /v2/scheduler/posts` with `userId` and `blogId` query parameters and an `X-Mc-Auth` token header. All of it is from memory and UNVERIFIED. API access may depend on the plan. Do not rely on this adapter until you have tested it with a real account.
