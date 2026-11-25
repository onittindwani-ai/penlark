# Operating and backups

## Backups

- **Database.** Postgres: `deploy/hetzner/backup.sh` or your host's managed backups. SQLite: copy the `.sqlite3` file while the API is stopped, or use `sqlite3 penlark.sqlite3 ".backup backup.sqlite3"`.
- **Exports.** The exports volume holds saved drafts, and `deploy/hetzner/backup.sh` copies it too. Your writing samples, notes and profiles live in the database, so the database backup covers them. Backup files hold your clients' writing: keep them readable by their owner only.
- **Settings.** Keep the `.env` file in a password manager, never in Git.

## Test a restore

1. Make a new empty database.
2. Restore the dump into it. For Postgres: `pg_restore --no-owner -d NEWDB backup.dump` (or `psql` for a plain dump).
3. Start the API against it and sign in. Open the Library: the sample counts must match.
4. Open the Audit log and press **Check the chain**. It must say intact.

## Daily checks

- The worker is running (the learning loop on the Performance page refreshes every hour).
- The kill switch is off, and the banner shows the mode you expect.
- `python3 tools/doctor.py` prints no FAIL.

## Logs

The API logs request lines without bodies. Tokens, passwords and document text are not logged. If you add logging, keep it that way.

## Stopping and restarting

Stop the web app, then the worker, then the API. Start in the reverse order. Nothing is lost because every change is in the database.
