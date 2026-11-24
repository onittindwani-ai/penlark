# Troubleshooting

| What you see | Why | Fix |
|---|---|---|
| "The server is not reachable" | The web app cannot reach the API | Start the API. Check `API_BASE_URL`. |
| Sign in fails in demo | Wrong password | The demo password is `demo-password-1`, and only works while `DEMO_MODE=true`. |
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
