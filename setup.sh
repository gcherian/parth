#!/usr/bin/env bash
# setup.sh — Parth AI Server: one-shot setup for the new home at ~/Parth
# Run once after moving or cloning. Safe to re-run.

set -euo pipefail

PARTH_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$PARTH_DIR/server"
PYTHON=/opt/homebrew/bin/python3.11
PORT=8000
LOG=/tmp/parth_demo.log
PIDFILE=/tmp/parth.pid

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
info() { echo -e "  $*"; }
die()  { echo -e "${RED}  ✗ $*${NC}"; exit 1; }

echo ""
echo -e "${BOLD}  ╔═══════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║      PARTH AI  —  setup.sh        ║${NC}"
echo -e "${BOLD}  ╚═══════════════════════════════════╝${NC}"
echo ""

cd "$SERVER_DIR"

# ── 1. Python venv ────────────────────────────────────────────────────────────
if [ ! -f "$SERVER_DIR/venv/bin/uvicorn" ]; then
    info "Creating Python virtual environment..."
    [ -f "$PYTHON" ] || die "Python 3.11 not found at $PYTHON — install via: brew install python@3.11"
    $PYTHON -m venv "$SERVER_DIR/venv"
    source "$SERVER_DIR/venv/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet -r "$SERVER_DIR/requirements.txt"
    ok "Python venv created and deps installed"
else
    source "$SERVER_DIR/venv/bin/activate"
    ok "Python venv ready"
fi

# ── 2. .env file ─────────────────────────────────────────────────────────────
if [ ! -f "$SERVER_DIR/.env" ]; then
    warn ".env missing — creating from template"
    cat > "$SERVER_DIR/.env" << 'ENVEOF'
DATABASE_URL=postgresql://parth:parth_dev@localhost:5432/parth

# LLM backend — set ANTHROPIC_API_KEY to switch to Claude cloud
TUTOR_BACKEND=auto
DEFAULT_MODEL=gemma3:12b
FAST_MODEL=llama3.2:latest
OLLAMA_URL=http://localhost:11434
KRISHNA_MODEL=claude-haiku-4-5-20251001
KRISHNA_INTERVAL=10

PORT=8000
RATE_LIMIT=20
DAILY_REQUEST_CAP=200

# Security — leave empty for local dev (enforced only in production)
PARTH_API_KEY=
ADMIN_KEY=

DATA_DIR=/Users/george.cherian/Parth/server/data
ENVEOF
    ok ".env created — add ANTHROPIC_API_KEY to enable cloud mode"
else
    ok ".env exists"
fi

set -a; source "$SERVER_DIR/.env"; set +a

# ── 3. Postgres ───────────────────────────────────────────────────────────────
if pg_isready -U parth -d parth -q 2>/dev/null; then
    ok "Postgres ready"
else
    warn "Postgres not ready — starting via Docker..."
    if command -v docker &>/dev/null && [ -f "$SERVER_DIR/docker-compose.yml" ]; then
        docker compose -f "$SERVER_DIR/docker-compose.yml" up -d postgres
        for i in {1..20}; do
            pg_isready -U parth -d parth -q 2>/dev/null && break
            sleep 1
        done
        pg_isready -U parth -d parth -q 2>/dev/null && ok "Postgres ready" || die "Postgres failed to start"
    else
        die "Postgres not running and Docker not available. Start Postgres manually."
    fi
fi

# ── 4. DB schema ──────────────────────────────────────────────────────────────
python3 -c "
import asyncio, os, sys
sys.path.insert(0, '$SERVER_DIR')
os.chdir('$SERVER_DIR')
from foundation.db import apply_schema
asyncio.run(apply_schema())
" && ok "DB schema up to date" || warn "Schema apply failed — will retry on server start"

# ── 5. Ollama ─────────────────────────────────────────────────────────────────
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; print(', '.join(m['name'] for m in json.load(sys.stdin).get('models',[])))" 2>/dev/null)
    ok "Ollama ready  ($MODELS)"
else
    warn "Ollama not running — starting..."
    open -a Ollama 2>/dev/null || ollama serve >> /tmp/ollama.log 2>&1 &
    for i in {1..20}; do
        curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && break
        sleep 1
    done
    curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && ok "Ollama ready" || warn "Ollama not responding — server will start anyway"
fi

# ── 6. Kill any stale Parth process ──────────────────────────────────────────
if [ -f "$PIDFILE" ]; then
    OLD=$(cat "$PIDFILE")
    kill "$OLD" 2>/dev/null && warn "Stopped old server (pid $OLD)" || true
    rm -f "$PIDFILE"
fi
lsof -ti ":$PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

# ── 7. Sleep prevention ───────────────────────────────────────────────────────
sudo pmset -c sleep 0 disksleep 0 2>/dev/null && ok "Sleep prevention on" || warn "Run with sudo to prevent sleep during demo"

# ── 8. Start Parth ───────────────────────────────────────────────────────────
info "Starting Parth server..."
cd "$SERVER_DIR"
nohup uvicorn main:app --host 0.0.0.0 --port "$PORT" --log-level info > "$LOG" 2>&1 &
echo $! > "$PIDFILE"

echo -n "  Waiting for server"
for i in {1..30}; do
    if curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
        echo ""; ok "Parth is UP (pid $(cat $PIDFILE))"; break
    fi
    echo -n "."; sleep 1
done
curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1 || die "Server failed to start — check: tail -30 $LOG"

# ── 9. Banner ─────────────────────────────────────────────────────────────────
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "localhost")
BACKEND=$(curl -s http://localhost:$PORT/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tutor_backend','?'))" 2>/dev/null)
RAG=$(curl -s http://localhost:$PORT/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('rag_chunks',0))" 2>/dev/null)

echo ""
echo -e "${BOLD}  ┌─────────────────────────────────────────────────────────┐${NC}"
echo -e "${BOLD}  │               PARTH AI  —  READY  🇮🇳                    │${NC}"
echo -e "${BOLD}  ├─────────────────────────────────────────────────────────┤${NC}"
printf   "  │  %-56s│\n" "Backend : $BACKEND   RAG chunks: $RAG"
echo -e "${BOLD}  ├─────────────────────────────────────────────────────────┤${NC}"
printf   "  │  📊 Monitor  : http://%-34s│\n" "$LOCAL_IP:$PORT/monitor"
printf   "  │  🎮 Demo     : http://%-34s│\n" "$LOCAL_IP:$PORT/demo"
printf   "  │  🌍 World    : http://%-34s│\n" "$LOCAL_IP:$PORT/playground"
printf   "  │  🔬 Observer : http://%-34s│\n" "$LOCAL_IP:$PORT/observer"
printf   "  │  🕸  Graph   : http://%-34s│\n" "$LOCAL_IP:$PORT/graph"
printf   "  │  🪞 Mirror   : http://%-34s│\n" "$LOCAL_IP:$PORT/mirror"
printf   "  │  📖 API Docs : http://%-34s│\n" "$LOCAL_IP:$PORT/docs"
echo -e "${BOLD}  ├─────────────────────────────────────────────────────────┤${NC}"
printf   "  │  Logs  : %-47s│\n" "$LOG"
printf   "  │  Stop  : kill \$(cat $PIDFILE)%-30s│\n" ""
echo -e "${BOLD}  └─────────────────────────────────────────────────────────┘${NC}"
echo ""
