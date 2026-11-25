# Changelog

## 1.0.1 (2026-11-25)
- Hardening after a security review. The public demo password, the made up approver and viewer accounts, the demo buttons and the data reset now exist only while `DEMO_MODE` is on and no `OWNER_PASSWORD_HASH` is set. Setting the hash switches them off even if `DEMO_MODE` stays on, and the demo clock goes with them. The reset never erases the audit log and is refused on a server database. The API and the worker refuse an unsafe start (an example or short `SESSION_SECRET`, a demo on Postgres, the example `OWNER_EMAIL` with `MODE=live`) before the database is opened or anything is written.
- An approval is for the exact words. The approver now sees every character of a draft (it was the first 1,200), the approval keeps a fingerprint of the text, and deciding, planning on the calendar, exporting and sending are refused when the text changed. On Postgres the draft row is locked while it is edited or decided. An approval made before this release has no fingerprint: its draft cannot be exported until a second person approves it again. The API accepts a new approval request for such a draft; the Studio's Ask for approval button stays switched off while a draft shows as approved, so the request has to be made through the API until that is changed.
- Text that could freeze the app: banned patterns need an upper limit on every repeat and no repeat inside a repeat (refused when added, shown and skipped if already stored), the placeholder check and the markdown, transcript and X archive readers use bounded patterns, and uploads are read while they arrive (8 MB) off the main thread.
- Sign in: the email is compared without spaces or capitals for the limit and the lookup, with limits per address, per account and per address and account, field sizes are capped, and an unknown email costs the same work as a wrong password. The public click route uses the address uvicorn resolved, never the typed `X-Forwarded-For`; the web app passes on only the last address. The lead webhook and uploads are read in small pieces and refused as soon as they are too large, and a signature header with a strange character is a plain 401.
- Sending: a draft is claimed before the scheduling tool is called, so a second request cannot send it twice, and a draft saved at the scheduling tool is not sent again. A vendor timeout or error is said plainly, nothing is recorded as sent and the draft goes back. The kill switch set in the app now also stops the file export. A send no longer changes the shared adapter. Unknown platforms and dates are refused. The changes that were missing from the audit log (a rule deleted, an idea dropped, a plan removed, experiments, edits) are now recorded.
- A real install works end to end: add a voice from the app (Studio, Library and Voice profile pages) or with `python -m penlark.admin add-voice`, the built in banned phrases are saved on every start, and the owner, the timezone (`TIMEZONE`) and the allowed link hosts are settings. A tracked link host in `REDIRECT_ALLOW_HOSTS` now means exactly that host (write `*.example.com` for subdomains), and an empty list allows nothing outside the demo. Every setting is in `.env.example` and `docs/04-ENVIRONMENT-VARIABLES.md`, and a test fails when they drift apart. The API, worker, database migration and admin commands read the same settings file (`ENV_FILE`), and the demo data folder is found through `SEED_DIR` first, so an installed copy starts.
- Deploy: the Caddy API host serves only the lead webhook and `/health`; the Hetzner backup is private to its owner, keeps the exports folder and refuses an empty dump; the server installs Docker from Ubuntu's own packages. Docs say plainly what was and was not run (the workflow builds the images and starts the stack on GitHub; no real host was used).
- Web: an error page with a retry button, a form to add the first voice, and the approval page shows the whole draft.
- Tests: new tests for every fix. Nothing that tested a safe behaviour was removed.

## Earlier changes in 1.0.0 (round 5, a walk through every screen)
- A draft that was edited after it was sent for approval can no longer be approved: the edit withdraws the request (shown under Decided with its reason), and approving checks the draft and the house rules again. The demo draft that waits for a second person has finished text, no brackets.
- The voice you pick in the Studio is saved with the draft. Unsaved changes are shown and asked about before another draft opens. A viewer sees the draft read only and every write control switched off with a reason.
- Duplicates are refused with a reason: the same banned phrase, the same writing sample (pasted or in a file), the same post numbers imported twice, the same tracked link made twice. Empty files, a stray word and unsupported file types are refused as samples.
- Exporting a planned draft keeps one calendar entry on its planned day and platform. The Studio can copy the text.
- Phone top bar keeps Pause all and Sign out; the kill switch button and banner say what it stops; the palette runs actions (theme, sign out, kill switch, run, clock, reset); G then a number goes to a page; sign in returns to the page that was asked for.
- Tables line up their columns with their headers on every row; row buttons show on touch screens; tables whose rows open nothing no longer say enter opens. Files dropped on the Library or the CSV import go to a drop zone, a drop anywhere else no longer makes the browser leave the app.
- Plain words for the audit log (with a detail sheet), the integrations page (no raw category names) and the calendar week. Short links show the address the app is open on.

## Earlier changes in 1.0.0 (round 4, part M)
- Model path for the voice guide, draft variants and idea finder (`model_tasks.py`), selected by `LLM_BACKEND` plus `GUIDE_WRITER`, `DRAFT_WRITER`, `IDEA_FINDER`. Code re scores every model draft, a model cannot approve or schedule, live use UNVERIFIED. Local fake server and recorded fixtures.
- The approval request now refuses a draft under the minimum voice match.
- Banned phrases match hyphens, curly apostrophes and word endings; 34 more stock phrases; narrower client claims, number words as figures, more experience verbs; better stemmer for the idea finder.
- Independent held out sets A and B, scorer `tools/eval_independent.py`, `docs/INDEPENDENT-EVAL.md`.
- Contract tests for the scheduler adapters against published descriptions (Postiz OpenAPI; Metricool and Buffer partly). `tools/doctor.py` repaired.

## Earlier changes in 1.0.0 (first rounds)

- Renamed from Voiceprint to Penlark after a public name check. The Python package, environment variable prefix, interface text, documents, prompts, templates and screenshots all use the new name.
- Read only sign in: `VIEWER_EMAIL` and `VIEWER_PASSWORD_HASH` (demo `viewer@example.test`). It opens every page and changes nothing.
- Approvals are decided by the base rule: the person who asked cannot decide. The route's own check is removed.
- `LLM_BACKEND` (offline, fixture, anthropic) replaces `LLM_MODE`. The offline template writer sits behind the same request shape a model will use (`offline_llm.py`). The model writer itself is still to come.
- `LOGIN_BURST` setting for the sign in limit (default 5; the browser tests raise it).
- Posting rhythm: `CADENCE` (default `linkedin:2,x:2`), `GET /api/cadence`, and a rhythm strip and platform picker on the Calendar. A plan and a nudge, never a block.
- Decided defaults replace the founder fact tags: reading level grade 9 or lower (was 12; a text under 8 words is not judged on reading level), dashes banned in marketing text and configurable, voice match 60, tracked link hosts as an allow list the implementer sets.
- Guide 10 is `10-USING-IT-FOR-A-CLIENT.md` (what to charge for, onboarding, handover, contract points).

## 1.0.0
First release. Studio with a live voice match meter, voice fingerprint radar, ideas with verified quotes, house rules with a claims check, approval queue with a second person, file export and Postiz, Buffer and Metricool adapters (tested against local stand ins only), performance import and a learning loop, tracked links with an allow list, signed lead webhook, A/B experiments, audit log. Base 1.1.1.
