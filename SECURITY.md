# Security

## Report a problem
Open a private security advisory on the repository, or email the address in the repository profile. Do not post a secret or a vulnerability in a public issue.

## What was checked
Secret scan, `pip-audit` and `pnpm audit`, signature tests for the lead webhook, an open redirect test set (including fuzzing), a base URL guard for scheduler hosts, an approval rule that stops a person approving their own request, draft mode and kill switch tests, a damaged PDF test, prompt injection style text in notes.

## What is not done
No independent test. No second factor login. Rate limits are in memory, for one process. PDF reading runs in the API process. Screen readers were not used. The scheduler adapters were never run against the real services. Click visitor tokens are day scoped hashes, not a full privacy review. Review `docs/13-SECURITY-AND-DATA.md` before you store a client's writing.
