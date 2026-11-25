# Security

## Report a problem
Use the Security tab of the repository and choose **Report a vulnerability**. It opens a private advisory that only the maintainers can read. We aim to acknowledge it within 5 working days. Do not post a secret or a vulnerability in a public issue.

## Two risks to know before you use it
- **Demo mode is public on purpose.** With `DEMO_MODE=true` and no owner password, anyone who can reach the app can sign in with the published demo password and press the demo buttons, including the data reset. Never expose a demo to the internet with real writing in it. Setting `OWNER_PASSWORD_HASH` switches the demo shortcuts off.
- **A secret pasted anywhere is lost.** If a key or the `SESSION_SECRET` ends up in a chat, an issue, a screenshot or Git, make a new one and revoke the old one at once. The `.env` file is never committed.

## What was checked
Secret scan, `pip-audit` and `pnpm audit`, signature tests for the lead webhook, an open redirect test set (including fuzzing), a base URL guard for scheduler hosts, an approval rule that stops a person approving their own request and ties each approval to the exact text, draft mode and kill switch tests (the switches set in the app are read from the database), demo shortcut tests, sign in limit tests, hostile text and pattern tests with a time limit, a damaged PDF test, prompt injection style text in notes.

## What is not done
No independent test. No second factor login. Rate limits are in memory, for one process. PDF reading runs in the API process. The GitHub workflow builds the Docker images and starts the stack on a GitHub machine, but no real host (Hetzner, Railway, Vercel) was ever deployed to. Screen readers were not used. The scheduler adapters were never run against the real services. Click visitor tokens are day scoped hashes, not a full privacy review. Review `docs/13-SECURITY-AND-DATA.md` before you store a client's writing.
