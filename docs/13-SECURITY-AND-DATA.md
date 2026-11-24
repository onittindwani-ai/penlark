# Security and data

- **Sign in** is required on every route except the sign in, the tracked link redirect and the signed lead webhook. Passwords are argon2 hashes. Sessions are signed, expire, and live in an httpOnly cookie set by the web app, which forwards to a private API.
- **Two people.** The person who asks for an approval cannot decide it. The shared base refuses it (the same person cannot ask and decide) and a test in Penlark checks it through the route.
- **Nothing publishes by itself.** Draft mode sends nothing. A send needs live mode, an approved draft and an explicit confirm. The kill switch wins over live mode, and the app can only pull the mode back, never push it forward.
- **Untrusted text.** Notes, comments and emails are data. They are checked as text and never trigger an action. In the live model path they are passed through the shared untrusted wrapper.
- **No open redirect.** A tracked link can only point at a host on your allow list, over https. The target is stored when the link is made and checked again on every click. The click request cannot change it.
- **Visitor privacy.** A click stores a hash of address, browser and date, never an address. The same person on another day counts as a new visitor.
- **Lead webhook.** HMAC SHA 256 signature, a size cap, and duplicate events ignored.
- **Audit log.** Every change is chained to the one before. The Audit page can check the chain.
- **Secrets.** Never printed, never stored in the database. `tools/scan_secrets.py` scans the repo.
- **What stays on the vendor side.** Posts and tokens held by Postiz, Buffer or Metricool are governed by their own terms.

Your writing samples are stored in the database in plain text, because the engine measures them. Protect the database like the writing itself. Back up and delete it when the client leaves.
