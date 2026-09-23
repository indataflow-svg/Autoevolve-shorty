#!/usr/bin/env bash
# Restore entry point. Default mode verifies the archive only; nothing near
# the live instance is touched unless --apply is passed (and that refuses to
# run while the target looks live, unless --force).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${PYTHON:-}" ]; then
    PY="$PYTHON"
elif [ -x "$DIR/../.venv/bin/python" ]; then
    PY="$DIR/../.venv/bin/python"
else
    PY="python3"
fi
exec "$PY" "$DIR/restore.py" "$@"
