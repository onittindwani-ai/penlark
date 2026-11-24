# Go live checklist

1. `DEMO_MODE=false`, real `SESSION_SECRET`, owner and approver emails and password hashes. `python3 tools/doctor.py` shows no PROBLEM.
2. Load the person's real writing (15 or more samples) and build the profile. Read the guide, edit it, lock it.
3. Read the voice match numbers in `EVALUATION.md`: they came from short fictional texts, so score some of the person's own held back posts before you trust the meter.
4. Add the person's own banned phrases and the facts they will never claim (House rules).
5. Add notes with real numbers as `fact` notes. Drafts can only use numbers that appear there.
6. Set `REDIRECT_ALLOW_HOSTS` and `LEAD_WEBHOOK_SECRET`. Send one signed test event.
7. Keep `MODE=draft` and use the file export for the first week.
8. Pick a scheduler, test with one real account, keep `saveToDraft` on, then consider `MODE=live`.
9. Check the Audit log chain, and that the kill switch banner works.
10. Write down who approves, and what happens if they are away.
