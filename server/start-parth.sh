#!/usr/bin/env bash
# start-parth.sh — idempotent Parth server starter
# Safe to run multiple times; will not create duplicate processes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=8000
PIDFILE="/tmp/parth.pid"
LOG="/tmp/parth_server.log"

cd "$SCRIPT_DIR"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
die()  { echo -e "${RED}  ✗ $*${NC}"; exit 1; }

echo ""
echo "  PARTH — start-parth.sh"
echo "  ──────────────────────"

# ── Already running? ──────────────────────────────────────────────────────────
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        ok "Server already running (pid $OLD_PID) — nothing to do"
        echo ""
        curl -s "http://localhost:$PORT/health" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(f'  status={d[\"status\"]} model={d[\"default_model\"]}')" 2>/dev/null || true
        echo ""
        exit 0
    else
        warn "Stale PID file — cleaning up"
        rm -f "$PIDFILE"
    fi
fi

# Belt-and-suspenders: check the port directly too
if lsof -i ":$PORT" -sTCP:LISTEN -t &>/dev/null; then
    EXISTING=$(lsof -i ":$PORT" -sTCP:LISTEN -t | head -1)
    ok "Port $PORT already in use by pid $EXISTING — nothing to do"
    exit 0
fi

# ── Postgres ──────────────────────────────────────────────────────────────────
if pg_isready -U parth -d parth -q 2>/dev/null; then
    ok "Postgres ready"
else
    warn "Postgres not ready — starting via brew services"
    brew services start postgresql@14 2>/dev/null || true
    for i in {1..15}; do
        pg_isready -U parth -d parth -q 2>/dev/null && break
        sleep 1
    done
    pg_isready -U parth -d parth -q 2>/dev/null && ok "Postgres ready" || die "Postgres failed to start"
fi

# ── Ollama ────────────────────────────────────────────────────────────────────
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    ok "Ollama ready"
else
    warn "Ollama not running — starting"
    open -a Ollama 2>/dev/null || ollama serve >>/tmp/ollama.log 2>&1 &
    for i in {1..20}; do
        curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && break
        sleep 1
    done
    curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && ok "Ollama ready" || die "Ollama failed to start"
fi

# ── Tailscale ─────────────────────────────────────────────────────────────────
if tailscale status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('BackendState')=='Running' else 1)" 2>/dev/null; then
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
    ok "Tailscale connected — $TS_IP"
else
    warn "Tailscale not connected — phone will only work on same WiFi"
fi

# ── Sleep prevention ──────────────────────────────────────────────────────────
sudo pmset -c sleep 0 disksleep 0 2>/dev/null && ok "Sleep prevention on" || warn "Run with sudo to prevent sleep"

# ── Venv ──────────────────────────────────────────────────────────────────────
[ -d "venv" ] || die "venv missing — run ./setup.sh first"
source venv/bin/activate

# ── Apply DB schema (idempotent — CREATE IF NOT EXISTS) ───────────────────────
python3 -c "
import asyncio
from foundation.db import apply_schema
asyncio.run(apply_schema())
" && ok "DB schema up to date" || warn "Schema apply failed — server may still work"

# ── Banner ────────────────────────────────────────────────────────────────────
TS_IP=$(tailscale ip -4 2>/dev/null || echo "no-tailscale")
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "localhost")
echo ""
echo "  ┌───────────────────────────────────────────┐"
echo "  │           PARTH AI SERVER                 │"
echo "  ├───────────────────────────────────────────┤"
printf "  │  Local   : http://%-24s│\n" "$LOCAL_IP:$PORT"
printf "  │  Tailscale: http://%-24s│\n" "$TS_IP:$PORT"
echo "  │  Health  : /health  Docs: /docs           │"
echo "  └───────────────────────────────────────────┘"
echo ""

# ── Start with auto-restart loop ──────────────────────────────────────────────
(
    while true; do
        uvicorn main:app --host 0.0.0.0 --port "$PORT" --log-level info >> "$LOG" 2>&1
        EXIT=$?
        echo "[$(date)] Server exited (code $EXIT) — restarting in 5s" >> "$LOG"
        sleep 5
    done
) &
SERVER_PID=$!
echo $SERVER_PID > "$PIDFILE"

# Wait for the server to accept connections
echo -n "  Waiting for server"
for i in {1..30}; do
    if curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
        echo ""
        ok "Server up (pid $SERVER_PID) — logs: $LOG"
        echo ""
        exit 0
    fi
    echo -n "."
    sleep 1
done
echo ""
die "Server did not come up after 30s — check $LOG"
