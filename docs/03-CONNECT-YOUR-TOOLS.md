# Connect your tools

Penlark works with no connection at all (file export). Everything below is optional. Settings are environment variables on the server, never typed into the web app. Every adapter here is tier B: written from public docs or memory and tested only against local stand ins in `mock/`. None has run against the real service.

## Postiz (open source scheduler)
1. Run Postiz yourself or use its cloud, connect your networks inside Postiz, and create an API key in its settings.
2. Set `SCHEDULER_ADAPTER=postiz`, `POSTIZ_API_KEY` and, for a self hosted one, `POSTIZ_BASE_URL` (the public API path ends in `/public/v1`). The address must be https and public: a plain http address, `localhost` or a private network address is refused unless you also set `ALLOW_PRIVATE_SCHEDULER=true` (off by default, listed in the settings problems while on, for a Postiz you run yourself on your own network). The host is looked up each time Penlark calls it, not at start, so a name server hiccup while the app restarts does not stop it.
3. The key goes in the `Authorization` header with no Bearer prefix (read from the Postiz docs on 2026-11-23). The default limit is 90 create requests an hour.
4. Find your channel id inside Postiz. Penlark needs it for every send.

## Buffer
1. Create a token in the Buffer settings for the API. The developer docs on 2026-11-23 show a GraphQL endpoint with a Bearer token.
2. Set `SCHEDULER_ADAPTER=buffer` and `BUFFER_TOKEN`.
3. A send saves a draft by default (`saveToDraft`). A person still presses publish inside Buffer.

## Metricool
1. Set `SCHEDULER_ADAPTER=metricool`, `METRICOOL_TOKEN`, `METRICOOL_USER_ID` and `METRICOOL_BLOG_ID`.
2. The request shape could not be read from the docs and is from memory: UNVERIFIED. API access may need a paid plan.

## Lead events (attribution)
1. Set `LEAD_WEBHOOK_SECRET` to a long random string and give the API a public address.
2. From your form or CRM tool, send `POST /api/webhooks/lead` with a JSON body `{"lead_ref": "...", "kind": "lead", "link_code": "..."}` and the header `x-penlark-signature: sha256=<hex of an HMAC SHA 256 of the raw body with your secret>`.
3. A repeat of the same `lead_ref` and `kind` is ignored, so a retry cannot count twice.

## Tracked links
Set `PUBLIC_BASE_URL` to where the web app lives and `REDIRECT_ALLOW_HOSTS` to the hosts your links may point at (your own site). A link to any other host is refused.

## Platform approvals
LinkedIn, X, Instagram and the other networks each need their own app approval before anything can post through an API. The scheduler tool holds that approval. Penlark does not talk to a network directly.

## Other tools
For a scheduler or link tool we did not build, use the recipe prompts in `../prompts/04-recipes.md`.
