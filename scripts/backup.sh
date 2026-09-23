#!/usr/bin/env bash
# Online-safe backup entry point (cron/Make friendly).
# Database files are snapshotted with the SQLite backup API, never `cp`.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${PYTHON:-}" ]; then
    PY="$PYTHON"
elif [ -x "$DIR/../.venv/bin/python" ]; then
    PY="$DIR/../.venv/bin/python"
else
    PY="python3"
fi
exec "$PY" "$DIR/backup.py" "$@"
