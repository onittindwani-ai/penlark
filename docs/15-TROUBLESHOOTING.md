# Troubleshooting

| What you see | Why | Fix |
|---|---|---|
| "The server is not reachable" | The web app cannot reach the API | Start the API. Check `API_BASE_URL`. |
| Sign in fails in demo | Wrong password | The demo password is `demo-password-1`, and only works while `DEMO_MODE=true` and `OWNER_PASSWORD_HASH` is empty. |
| The API or worker stops at start and lists settings | The settings are not safe to run | Read the list: an example or short `SESSION_SECRET`, a demo on a Postgres database, or the example `OWNER_EMAIL` with `MODE=live`. Fix each and start again. |
| The app is empty after the first sign in | A new install has no voice yet | Press Add a voice, or run `python -m penlark.admin add-voice "Name"`. |
| "The kill switch is on, so nothing was exported" | The switch in the app (or `KILL_SWITCH=true`) is on | Turn it off in settings, or on the top bar. |
| "The text is not the text that was approved" | The draft changed after it was approved | Ask a second person to approve this version. |
| A rule says "was not run" | A banned pattern was too wide to run safely | Edit or delete it on the Rules page: give every repeat an upper limit, for example `\w{1,40}`. |
| A draft shows "being sent" for long | The app stopped during a send | It frees itself after 30 minutes (the audit log records it). Check the scheduling tool for the post before you send again: if the post is there, sending again would make a second one. |
| Every request answers 401 | `SESSION_SECRET` differs between web and API, or the cookie is blocked | Use the same value. On http localhost set `INSECURE_COOKIES=1`. |
| "Ask a second person to approve" | The asker tried to approve | Sign in as the approver. |
| "Fill the [BRACKETS]" | The draft still has placeholders | Replace each bracket with your own words. |
| "Needs a source or a founder fact" | A number or claim has no matching note | Attach the note, link it to the line, or remove the line. |
| "That address is not on your allow list" | The link host is not allowed | Add it to `REDIRECT_ALLOW_HOSTS`. |
| "Nothing was sent: MODE is draft" | Draft mode | Use the file export, or follow doc 09 before `MODE=live`. |
| Meter says the number is rough | Under 25 words | Write more. |
| PDF upload fails | A scan with no text | Paste the text instead. |
| Build cannot find `@sendora/ui-kit` | Workspace not installed | `pnpm install` from the repo root. |

Run `python3 tools/doctor.py` first. It names the problem without printing a secret.
