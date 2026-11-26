# Go live checklist

1. `DEMO_MODE=false`, real `SESSION_SECRET` (32 or more characters), `OWNER_EMAIL` that is not the example address (a live start is refused otherwise), owner and approver emails and password hashes, and your `TIMEZONE`. `python3 tools/doctor.py` shows no PROBLEM.
2. Add the voice (Add a voice, or `.venv/bin/python -m penlark.admin add-voice`), load the person's real writing (15 or more samples) and build the profile. Read the guide, edit it, lock it.
3. Read the voice match numbers in `EVALUATION.md`: they came from short fictional texts, so score some of the person's own held back posts before you trust the meter.
4. Add the person's own banned phrases and the facts they will never claim (House rules).
5. Add notes with real numbers as `fact` notes. Drafts can only use figures that appear there as the same whole figure (a note with `15 percent` does not source a claim of `5 percent`).
6. Set `REDIRECT_ALLOW_HOSTS` (a plain entry means exactly that host; write `*.example.com` for subdomains) and `LEAD_WEBHOOK_SECRET`. Send one signed test event.
7. Keep `MODE=draft` and use the file export for the first week.
8. Pick a scheduler, test with one real account, keep `saveToDraft` on, then consider `MODE=live`.
9. Check the Audit log chain, and that the kill switch banner works: with it on, a send and a file export are both refused. If the app stops while a draft shows "being sent", after 30 minutes the draft is held as "send unclear" and the audit log says so: look in the scheduling tool for the post, then press **It was posted** or **It was not posted**. If a draft shows "send unclear", open the tool, look for the post, and press **It was posted** or **It was not posted** in the Studio.
10. Write down who approves, and what happens if they are away.
