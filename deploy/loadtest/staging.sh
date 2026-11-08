#!/usr/bin/env bash
# Disposable staging instance for load tests: same code, its own data/ copy.
#
#   deploy/loadtest/staging.sh start     # copy code+data to /tmp, serve :8788
#   deploy/loadtest/staging.sh stop      # kill it and remove the copy
#
# Why a copy: the live databases are under data/ and are the product. A load
# test must never write to them, and a staging copy also lets a destructive
# scenario be run deliberately. Only the bootstrap/world-data files are shared,
# and endpoints exercised by loadtest.py are read-only anyway.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="${STAGE_DIR:-/tmp/autoevolve-loadtest}"
PORT="${PORT:-8788}"
WORKERS="${WORKERS:-1}"
PID_FILE="$STAGE/.uvicorn.pid"

stop() {
    if [ -f "$PID_FILE" ]; then
        kill "$(cat "$PID_FILE")" 2>/dev/null || true
        rm -f "$PID_FILE"
    fi
    # --workers spawns children; be thorough.
    pkill -f "uvicorn app.api:app --host 127.0.0.1 --port ${PORT}" 2>/dev/null || true
    rm -rf "$STAGE"
    echo "staging stopped (${STAGE})"
}

start() {
    rm -rf "$STAGE"
    mkdir -p "$STAGE"
    tar -C "$SRC" \
        --exclude=.git --exclude=.venv --exclude=node_modules --exclude=engines \
        --exclude=videos --exclude=backups --exclude='data/renders' --exclude='__pycache__' \
        -cf - . | tar -C "$STAGE" -xf -
    ln -s "$SRC/.venv" "$STAGE/.venv"
    cd "$STAGE"
    setsid nohup .venv/bin/python -m uvicorn app.api:app \
        --host 127.0.0.1 --port "$PORT" --workers "$WORKERS" \
        > "$STAGE/uvicorn.log" 2>&1 < /dev/null &
    echo $! > "$PID_FILE"
    for _ in $(seq 1 40); do
        if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/health" 2>/dev/null; then
            echo "staging ready: http://127.0.0.1:${PORT} (workers=${WORKERS}, data copy at ${STAGE}/data)"
            return 0
        fi
        sleep 1
    done
    echo "staging did not become ready; last log lines:" >&2
    tail -20 "$STAGE/uvicorn.log" >&2 || true
    exit 1
}

case "${1:-}" in
    start) start ;;
    stop) stop ;;
    *) echo "usage: staging.sh start|stop" >&2; exit 2 ;;
esac
