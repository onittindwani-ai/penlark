#!/bin/sh
# Daily Postgres backup. Run from the repository folder: deploy/hetzner/backup.sh
set -eu
OUT=/var/backups/penlark
mkdir -p "$OUT"
STAMP=$(date +%Y%m%d-%H%M)
docker compose exec -T db pg_dump -U penlark -Fc penlark > "$OUT/penlark-$STAMP.dump"
# keep the newest 14 dumps
ls -1t "$OUT"/penlark-*.dump | tail -n +15 | while read -r old; do rm -f -- "$old"; done
echo "wrote $OUT/penlark-$STAMP.dump"
