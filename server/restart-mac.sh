#!/usr/bin/env bash
# restart-mac.sh — post-reboot or recovery reset for the Parth dev machine.
# Idempotent: safe to run at any time, whether services are up or down.
# Run this after Mac restarts, after crashes, or just to verify state.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="/tmp/parth.pid"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
die()  { echo -e "${RED}  ✗ $*${NC}"; exit 1; }

echo ""
echo "  PARTH — restart-mac.sh"
echo "  ──────────────────────"
echo "  $(date)"
echo ""

# ── 1. Kill stale / unwanted processes ───────────────────────────────────────
echo "  [1/5] Cleaning stale processes"

# Cloudflared — replaced by Tailscale
if pgrep -x cloudflared >/dev/null 2>&1; then
    pkill -x cloudflared && warn "cloudflared killed (use Tailscale instead)"
else
    ok "No cloudflared running"
fi

# Old Parth server (uvicorn) — will be restarted cleanly
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null && warn "Old server (pid $OLD_PID) stopped"
        sleep 2
    fi
    rm -f "$PIDFILE"
fi
# Belt-and-suspenders: kill any uvicorn on port 8000
EXISTING_PID=$(lsof -i :8000 -sTCP:LISTEN -t 2>/dev/null | head -1 || true)
if [ -n "$EXISTING_PID" ]; then
    kill "$EXISTING_PID" 2>/dev/null && warn "Killed process $EXISTING_PID on :8000"
    sleep 1
fi
ok "Port 8000 clear"

# ── 2. Postgres ───────────────────────────────────────────────────────────────
echo "  [2/5] Postgres"
if pg_isready -U parth -d parth -q 2>/dev/null; then
    ok "Postgres already running"
else
    brew services start postgresql@14 2>/dev/null || true
    for i in {1..15}; do
        pg_isready -U parth -d parth -q 2>/dev/null && break
        sleep 1
    done
    pg_isready -U parth -d parth -q && ok "Postgres started" || die "Postgres failed"
fi

# ── 3. Ollama ─────────────────────────────────────────────────────────────────
echo "  [3/5] Ollama"
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    MODELS=$(curl -sf http://localhost:11434/api/tags | python3 -c \
        "import sys,json; ms=json.load(sys.stdin).get('models',[]); print(', '.join(m['name'] for m in ms[:3]))" 2>/dev/null || echo "unknown")
    ok "Ollama running — $MODELS"
else
    open -a Ollama 2>/dev/null || warn "Could not open Ollama.app — start it manually"
    for i in {1..20}; do
        curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && break
        sleep 1
    done
    curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && ok "Ollama ready" || warn "Ollama not responding — check manually"
fi

# ── 4. Tailscale ──────────────────────────────────────────────────────────────
echo "  [4/5] Tailscale"
if tailscale status --json 2>/dev/null | python3 -c \
    "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('BackendState')=='Running' else 1)" 2>/dev/null; then
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
    ok "Tailscale connected — $TS_IP"
else
    warn "Tailscale not connected — open the Tailscale menu bar app"
    warn "Phone connectivity will fail until Tailscale is up"
fi

# ── 5. Sleep prevention ───────────────────────────────────────────────────────
echo "  [5/5] Sleep prevention"
sudo pmset -c sleep 0 disksleep 0 2>/dev/null && ok "Sleep disabled on AC power" \
    || warn "Could not set pmset — run: sudo pmset -c sleep 0"

# ── Start Parth ───────────────────────────────────────────────────────────────
echo ""
echo "  Starting Parth server..."
echo ""
exec "$SCRIPT_DIR/start-parth.sh"
