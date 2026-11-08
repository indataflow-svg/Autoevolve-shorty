#!/usr/bin/env bash
# Unattended maintenance jobs, one entry point for cron/systemd timers.
#
#   deploy/daily-jobs.sh backup   # 02:00  snapshot + verify the SQLite files
#   deploy/daily-jobs.sh ingest   # 03:00  refresh EDGAR/CommonCrawl world data
#   deploy/daily-jobs.sh reload   # 04:00  graceful worker replacement
#   deploy/daily-jobs.sh cert     #        TLS renewal + nginx reload
#
# Nothing here deletes data. The only destructive operation in this system is
# `scripts/restore.sh`, run by a human against a verified archive.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/autoevolve}"
cd "$APP_DIR"

JOB="${1:?usage: daily-jobs.sh backup|ingest|reload|cert}"

# TLS, once enabled, lives in a compose override. Pick it up automatically so
# cron never forgets it.
COMPOSE_FILES=(-f deploy/compose.prod.yaml)
[ -f deploy/compose.tls.yaml ] && COMPOSE_FILES+=(-f deploy/compose.tls.yaml)

# Never let two runs of the same job overlap (a slow ingest must not stack).
exec 9>"/tmp/autoevolve-${JOB}.lock"
if ! flock -n 9; then
    echo "[$(date -Is)] $JOB already running, skipped"
    exit 0
fi

case "$JOB" in
    backup)
        ./scripts/backup.sh
        archive="$(ls -t backups/company-core-*.tar.gz 2>/dev/null | head -1)"
        if [ -z "$archive" ]; then
            echo "backup produced no archive" >&2
            exit 1
        fi
        .venv/bin/python scripts/verify_backup.py --archive "$archive"
        # Keep 14 days: snapshots are files, disk is finite.
        find backups -name 'company-core-*.tar.gz*' -mtime +14 -delete
        ;;
    ingest)
        .venv/bin/python scripts/ingest_worlddata.py
        ;;
    reload)
        # Rolling, graceful replacement: stop one worker at a time (nginx
        # routes around it immediately), let uvicorn finish what it accepted,
        # then start it and move on. Not request-count recycling — renders and
        # plan generation run for minutes and must not be aborted mid-flight.
        for id in $(docker compose "${COMPOSE_FILES[@]}" ps -q api); do
            docker stop -t "${DRAIN_SECONDS:-300}" "$id" >/dev/null
            docker start "$id" >/dev/null
            sleep "${ROLLING_PAUSE_SECONDS:-10}"
        done
        ;;
    cert)
        # Same lineage volume enable-tls.sh created, so renewal keeps renewing
        # the certificate nginx actually loads.
        docker run --rm \
            -v "$APP_DIR/deploy/tls:/etc/letsencrypt" \
            -v "$APP_DIR/deploy/certbot-www:/var/www/certbot" \
            certbot/certbot renew --quiet
        docker compose "${COMPOSE_FILES[@]}" exec -T nginx nginx -s reload
        ;;
    *)
        echo "unknown job: $JOB" >&2
        exit 2
        ;;
esac

echo "[$(date -Is)] $JOB done"
