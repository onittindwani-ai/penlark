# Troubleshooting

| What you see | Why | Fix |
|---|---|---|
| "The server is not reachable" | The web app cannot reach the API | Start the API. Check `API_BASE_URL`. |
| Sign in fails in demo | Wrong password | The demo password is `demo-password-1`, and only works while `DEMO_MODE=true` and `OWNER_PASSWORD_HASH` is empty. |
| The API or worker stops at start and lists settings | The settings are not safe to run | Read the list: an example or short `SESSION_SECRET`, a demo on a Postgres database, or the example `OWNER_EMAIL` with `MODE=live`. Fix each and start again. |
| The app is empty after the first sign in | A new install has no voice yet | Press Add a voice, or run `.venv/bin/python -m penlark.admin add-voice "Name"`. |
| "The kill switch is on, so nothing was exported" | The switch in the app (or `KILL_SWITCH=true`) is on | Turn it off in settings, or on the top bar. |
| "The text is not the text that was approved" | The draft changed after it was approved | Ask a second person to approve this version. |
| A rule says "was not run" | A banned pattern was too wide to run safely | Edit or delete it on the Rules page: give every repeat an upper limit, for example `\w{1,40}`. |
| A draft shows "being sent" for long | The app stopped during a send | After 30 minutes it is held as "send unclear" (the audit log records it). Look in the scheduling tool for the post, then press **It was posted** or **It was not posted**. It is never freed on its own, because sending again could make a second post. |
| A tracked link says "Too many people opened links" | The click limit was reached, or every visitor looks like one address | Wait a minute. If it happens to ordinary traffic, the API does not trust your proxy: the settings page then shows a `FORWARDED_ALLOW_IPS` warning (see `04`). |
| A post that was sent will not come off the calendar | Only a planned item can be taken off | A sent or exported row is a record, so a second send cannot happen by accident. Remove the post in the scheduling tool yourself. |
| A send says the tool "did not give a clear answer" although the tool answered | The tool answered with a success status but no post id (an error body or an empty list) | Look in the tool, then press **It was posted** or **It was not posted**. The message names what the tool said. |
| Every request answers 401 | The API's `SESSION_SECRET` was changed since you signed in (old sessions stop working), or the cookie is blocked | Sign in again. The web app does not hold the secret, so there is nothing to match. On http localhost set `INSECURE_COOKIES=1`. |
| Find ideas stays queued | The worker is not running | Start it (`make worker`, or the worker service in Docker). The Ideas page says so after a minute and a half. |
| A draft shows "send unclear, check the tool" | The scheduling tool timed out or sent an answer nobody could read, so the post may exist | Open the scheduling tool and look. In the Studio press **It was posted** or **It was not posted**. Nothing else can be done with the draft until you do. |
| The app stops at start with "made by an older version" | A SQLite file from an older Penlark lacks a column the code needs | See `12-UPDATING.md`: keep a copy and start a new file, or use Postgres. |
| "Ask a second person to approve" | The asker tried to approve | Sign in as the approver. |
| "Fill the [BRACKETS]" | The draft still has placeholders | Replace each bracket with your own words. |
| "Needs a source or a founder fact" | A number or claim has no matching note | Attach the note, link it to the line, or remove the line. |
| "That address is not on your allow list" | The link host is not allowed | Add it to `REDIRECT_ALLOW_HOSTS`. |
| "Nothing was sent: MODE is draft" | Draft mode | Use the file export, or follow doc 09 before `MODE=live`. |
| Meter says the number is rough | Under 25 words | Write more. |
| PDF upload fails | A scan with no text | Paste the text instead. |
| Build cannot find `@sendora/ui-kit` | Workspace not installed | `pnpm install` from the repo root. |

Run `python3 tools/doctor.py` first. It names the problem without printing a secret.
