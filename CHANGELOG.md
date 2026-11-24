# Changelog

## Unreleased (round 5, a walk through every screen)
- A draft that was edited after it was sent for approval can no longer be approved: the edit withdraws the request (shown under Decided with its reason), and approving checks the draft and the house rules again. The demo draft that waits for a second person has finished text, no brackets.
- The voice you pick in the Studio is saved with the draft. Unsaved changes are shown and asked about before another draft opens. A viewer sees the draft read only and every write control switched off with a reason.
- Duplicates are refused with a reason: the same banned phrase, the same writing sample (pasted or in a file), the same post numbers imported twice, the same tracked link made twice. Empty files, a stray word and unsupported file types are refused as samples.
- Exporting a planned draft keeps one calendar entry on its planned day and platform. The Studio can copy the text.
- Phone top bar keeps Pause all and Sign out; the kill switch button and banner say what it stops; the palette runs actions (theme, sign out, kill switch, run, clock, reset); G then a number goes to a page; sign in returns to the page that was asked for.
- Tables line up their columns with their headers on every row; row buttons show on touch screens; tables whose rows open nothing no longer say enter opens. Files dropped on the Library or the CSV import go to a drop zone, a drop anywhere else no longer makes the browser leave the app.
- Plain words for the audit log (with a detail sheet), the integrations page (no raw category names) and the calendar week. Short links show the address the app is open on.

## Unreleased (round 4, part M)
- Model path for the voice guide, draft variants and idea finder (`model_tasks.py`), selected by `LLM_BACKEND` plus `GUIDE_WRITER`, `DRAFT_WRITER`, `IDEA_FINDER`. Code re scores every model draft, a model cannot approve or schedule, live use UNVERIFIED. Local fake server and recorded fixtures.
- The approval request now refuses a draft under the minimum voice match.
- Banned phrases match hyphens, curly apostrophes and word endings; 34 more stock phrases; narrower client claims, number words as figures, more experience verbs; better stemmer for the idea finder.
- Independent held out sets A and B, scorer `tools/eval_independent.py`, `docs/INDEPENDENT-EVAL.md`.
- Contract tests for the scheduler adapters against published descriptions (Postiz OpenAPI; Metricool and Buffer partly). `tools/doctor.py` repaired.

## Unreleased

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
