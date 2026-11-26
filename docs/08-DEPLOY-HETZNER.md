# Deploy on a Hetzner server

**Not tested on Hetzner: no Hetzner server was created.** The GitHub workflow builds the Docker images and starts the compose stack on a GitHub machine, but nothing was deployed to a real host, and the Caddy and backup files were never run on one. Steps are UNVERIFIED, from our general knowledge. Check them against https://docs.hetzner.com. One small server runs everything with Docker Compose and Caddy, which gets an HTTPS certificate for you.

1. Make a server (Ubuntu LTS is fine). Add your SSH key while creating it.
2. Add a firewall that allows only ports 22, 80 and 443.
3. Point two DNS names at the server: one for the web app and one for the API. The API name is reached only by your form tool (the signed lead webhook) and an uptime check: Caddy answers 404 on every other address of it, so sign in and the rest of the API go through the web app.
4. Optional: paste `deploy/hetzner/cloud-init.yaml` into the cloud config box. It installs Docker and Compose from Ubuntu's own package repository (`docker.io` and `docker-compose-v2`, the names on Ubuntu 24.04), plus Caddy, and holds no secrets. Do not add any.
5. Log in with SSH and clone your repository to `/opt/penlark`.
6. `cp .env.example .env` and fill it in (see `04`): keep `DEMO_MODE=false`, set a `SESSION_SECRET` of 32 or more random characters, `OWNER_EMAIL`, `OWNER_PASSWORD_HASH` and `POSTGRES_PASSWORD` (letters and digits only, for example `openssl rand -hex 24`). Put your two DNS names in `deploy/hetzner/Caddyfile`.
7. `docker compose up -d --build`. The compose file already sets `FORWARDED_ALLOW_IPS` to the private network that holds the web container, so the rate limits see the real visitor. If you put the API behind your own proxy as well, set it to that proxy's address (never `*`).
8. Copy the Caddyfile to `/etc/caddy/Caddyfile` and `sudo systemctl reload caddy`.
9. Open the web address, sign in, and on the Integrations page press Test.

## Backups

`deploy/hetzner/backup.sh` writes a compressed Postgres dump and a copy of the exports folder to `/var/backups/penlark` (readable by its owner only: the files hold every writing sample, note and audit row). A failed dump is never kept as a backup. Run it daily with cron: `0 3 * * * /opt/penlark/deploy/hetzner/backup.sh`. Set `BACKUP_COPY_TO` to copy the files to another machine: a copy on the same disk is not a backup. Test a restore (see `11`) before you need it.
