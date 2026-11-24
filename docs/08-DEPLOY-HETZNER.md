# Deploy on a Hetzner server

**Not tested: no Hetzner server was created and no Docker image was built here (no Docker daemon).** The files in `deploy/hetzner/` are checked only for valid syntax. Steps are UNVERIFIED, from our general knowledge. Check them against https://docs.hetzner.com. One small server runs everything with Docker Compose and Caddy, which gets an HTTPS certificate for you.

1. Make a server (Ubuntu LTS is fine). Add your SSH key while creating it.
2. Add a firewall that allows only ports 22, 80 and 443.
3. Point two DNS names at the server: one for the web app and one for the API.
4. Optional: paste `deploy/hetzner/cloud-init.yaml` into the cloud config box. It installs Docker and Caddy and holds no secrets. Do not add any.
5. Log in with SSH and clone your repository to `/opt/penlark`.
6. `cp .env.example .env` and fill it in (see `04`), including `POSTGRES_PASSWORD`. Put your two DNS names in `deploy/hetzner/Caddyfile`.
7. `docker compose up -d --build`.
8. Copy the Caddyfile to `/etc/caddy/Caddyfile` and `sudo systemctl reload caddy`.
9. Open the web address, sign in, and on the Integrations page press Test.

## Backups

`deploy/hetzner/backup.sh` writes a compressed Postgres dump to `/var/backups/penlark`. Run it daily with cron: `0 3 * * * /opt/penlark/deploy/hetzner/backup.sh`. The exports volume holds saved drafts, so back it up too. Test a restore (see `11`) before you need it.
