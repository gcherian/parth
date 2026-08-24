#!/usr/bin/env bash
# setup.sh — Parth: one-shot build + start for macOS / Linux
#
# Usage:
#   ./setup.sh                 setup + start the server, prep the mobile app
#   ./setup.sh --server-only   skip the Flutter/mobile step entirely
#   ./setup.sh --mobile        also launch the Flutter app on a connected
#                              device/emulator (falls back to printing
#                              instructions if none is found)
#
# Safe to re-run — every step is idempotent.
#
# Requires: Python 3.11+, Docker (for Postgres), and optionally Ollama
# (local LLM) and Flutter (mobile app). Missing optional tools are skipped
# with a warning rather than failing the whole setup.

set -euo pipefail

PARTH_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$PARTH_DIR/server"
APP_DIR="$PARTH_DIR/app"
PORT="${PORT:-8000}"
LOG=/tmp/parth_server.log
PIDFILE=/tmp/parth.pid

MODE="server+mobile-prep"
for arg in "$@"; do
    case "$arg" in
        --server-only) MODE="server-only" ;;
        --mobile)      MODE="server+mobile-run" ;;
        *) echo "Unknown flag: $arg (expected --server-only or --mobile)"; exit 1 ;;
    esac
done

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

# ── 0. Find a usable Python (no hardcoded path — portable across machines) ──
PYTHON=""
for cand in python3.11 python3.12 python3.13 python3 python; do
    if command -v "$cand" &>/dev/null; then
        ver="$("$cand" -c 'import sys;print(sys.version_info[:2]>=(3,11))' 2>/dev/null || echo False)"
        if [ "$ver" = "True" ]; then PYTHON="$cand"; break; fi
    fi
done
if [ -z "$PYTHON" ]; then
    command -v python3 &>/dev/null && PYTHON=python3
fi
[ -n "$PYTHON" ] || die "Python 3.11+ not found. Install it (e.g. 'brew install python@3.11' on macOS, or your distro's package manager) and re-run."
info "Using $(command -v "$PYTHON") ($("$PYTHON" --version))"

cd "$SERVER_DIR"

# ── 1. Python venv ────────────────────────────────────────────────────────────
if [ ! -f "$SERVER_DIR/venv/bin/uvicorn" ]; then
    info "Creating Python virtual environment..."
    "$PYTHON" -m venv "$SERVER_DIR/venv"
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
    cat > "$SERVER_DIR/.env" << ENVEOF
DATABASE_URL=postgresql://parth:parth_dev@localhost:5432/parth

# LLM backend — set ANTHROPIC_API_KEY to switch to Claude cloud
TUTOR_BACKEND=auto
DEFAULT_MODEL=gemma3:12b
FAST_MODEL=llama3.2:latest
OLLAMA_URL=http://localhost:11434
KRISHNA_MODEL=claude-haiku-4-5-20251001
KRISHNA_INTERVAL=10

PORT=$PORT
RATE_LIMIT=20
DAILY_REQUEST_CAP=200

# Security — leave empty for local dev (enforced only in production)
PARTH_API_KEY=
ADMIN_KEY=

DATA_DIR=$SERVER_DIR/data
ENVEOF
    ok ".env created — add ANTHROPIC_API_KEY to it to enable cloud mode"
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
        for i in {1..30}; do
            pg_isready -U parth -d parth -q 2>/dev/null && break
            sleep 1
        done
        pg_isready -U parth -d parth -q 2>/dev/null && ok "Postgres ready" || die "Postgres failed to start — check: docker compose -f $SERVER_DIR/docker-compose.yml logs postgres"
    else
        die "Postgres not running and Docker not available. Install Docker Desktop, or start Postgres manually and set DATABASE_URL in server/.env."
    fi
fi

# ── 4. DB schema ──────────────────────────────────────────────────────────────
"$PYTHON" -c "
import asyncio, os, sys
sys.path.insert(0, '$SERVER_DIR')
os.chdir('$SERVER_DIR')
from foundation.db import apply_schema
asyncio.run(apply_schema())
" && ok "DB schema up to date" || warn "Schema apply failed — will retry on server start"

# ── 5. Ollama (optional — TUTOR_BACKEND=auto falls back to Claude cloud) ────
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    MODELS=$(curl -s http://localhost:11434/api/tags | "$PYTHON" -c "import sys,json; print(', '.join(m['name'] for m in json.load(sys.stdin).get('models',[])))" 2>/dev/null)
    ok "Ollama ready  ($MODELS)"
elif command -v ollama &>/dev/null; then
    warn "Ollama installed but not running — starting..."
    if [[ "$(uname)" == "Darwin" ]] && [ -d "/Applications/Ollama.app" ]; then
        open -a Ollama 2>/dev/null || true
    fi
    command -v ollama &>/dev/null && { ollama serve >> /tmp/ollama.log 2>&1 & } || true
    for i in {1..20}; do
        curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && break
        sleep 1
    done
    curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && ok "Ollama ready" || warn "Ollama not responding — set ANTHROPIC_API_KEY in server/.env to use Claude cloud instead"
else
    warn "Ollama not installed — set ANTHROPIC_API_KEY in server/.env to use Claude cloud instead (or: brew install ollama / https://ollama.com)"
fi

# ── 6. Kill any stale Parth process ──────────────────────────────────────────
if [ -f "$PIDFILE" ]; then
    OLD=$(cat "$PIDFILE")
    kill "$OLD" 2>/dev/null && warn "Stopped old server (pid $OLD)" || true
    rm -f "$PIDFILE"
fi
lsof -ti ":$PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

# ── 7. Sleep prevention (macOS only, best-effort) ────────────────────────────
if [[ "$(uname)" == "Darwin" ]]; then
    sudo -n pmset -c sleep 0 disksleep 0 2>/dev/null && ok "Sleep prevention on" || warn "Run 'sudo pmset -c sleep 0' yourself to prevent sleep during a demo"
fi

# ── 8. Start Parth server ────────────────────────────────────────────────────
info "Starting Parth server..."
cd "$SERVER_DIR"
nohup uvicorn main:app --host 0.0.0.0 --port "$PORT" --log-level info > "$LOG" 2>&1 &
echo $! > "$PIDFILE"

echo -n "  Waiting for server"
for i in {1..30}; do
    if curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
        echo ""; ok "Parth is UP (pid $(cat "$PIDFILE"))"; break
    fi
    echo -n "."; sleep 1
done
curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1 || die "Server failed to start — check: tail -30 $LOG"

# ── 9. Mobile app (Flutter) ──────────────────────────────────────────────────
if [ "$MODE" != "server-only" ]; then
    if command -v flutter &>/dev/null; then
        info "Preparing Flutter app..."
        ( cd "$APP_DIR" && flutter pub get >/tmp/parth_flutter.log 2>&1 ) \
            && ok "Flutter deps ready" \
            || warn "flutter pub get failed — see /tmp/parth_flutter.log"
        if [ "$MODE" = "server+mobile-run" ]; then
            if ( cd "$APP_DIR" && flutter devices 2>/dev/null | grep -qE '•.*•'); then
                info "Launching app on a connected device/emulator..."
                ( cd "$APP_DIR" && flutter run ) || warn "flutter run failed — run it yourself from $APP_DIR"
            else
                warn "No device/emulator detected. Start one (e.g. 'flutter emulators --launch <id>' or plug in a phone with USB debugging on) then run:  cd app && flutter run"
            fi
        else
            info "Mobile app deps are ready. To launch it: cd app && flutter run  (or pass --mobile to this script)"
        fi
    else
        warn "Flutter not installed — mobile app skipped. Install from https://docs.flutter.dev/get-started/install, then: cd app && flutter pub get && flutter run"
    fi
fi

# ── 10. Banner ────────────────────────────────────────────────────────────────
LOCAL_IP=$( (ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null) || (hostname -I 2>/dev/null | awk '{print $1}') || echo "localhost")
[ -n "$LOCAL_IP" ] || LOCAL_IP="localhost"
BACKEND=$(curl -s "http://localhost:$PORT/health" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print(d.get('tutor_backend','?'))" 2>/dev/null)
RAG=$(curl -s "http://localhost:$PORT/health" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print(d.get('rag_chunks',0))" 2>/dev/null)

echo ""
echo -e "${BOLD}  ┌─────────────────────────────────────────────────────────┐${NC}"
echo -e "${BOLD}  │               PARTH AI  —  READY  🇮🇳                    │${NC}"
echo -e "${BOLD}  ├─────────────────────────────────────────────────────────┤${NC}"
printf   "  │  %-56s│\n" "Backend : $BACKEND   RAG chunks: $RAG"
echo -e "${BOLD}  ├─────────────────────────────────────────────────────────┤${NC}"
printf   "  │  🌐 Web App  : http://%-34s│\n" "$LOCAL_IP:$PORT/"
printf   "  │  📊 Monitor  : http://%-34s│\n" "$LOCAL_IP:$PORT/monitor"
printf   "  │  🎮 Demo     : http://%-34s│\n" "$LOCAL_IP:$PORT/demo"
printf   "  │  🌍 World    : http://%-34s│\n" "$LOCAL_IP:$PORT/playground"
printf   "  │  📖 API Docs : http://%-34s│\n" "$LOCAL_IP:$PORT/docs"
echo -e "${BOLD}  ├─────────────────────────────────────────────────────────┤${NC}"
printf   "  │  📱 Mobile   : %-42s│\n" "cd app && flutter run"
echo -e "${BOLD}  ├─────────────────────────────────────────────────────────┤${NC}"
printf   "  │  Logs  : %-47s│\n" "$LOG"
printf   "  │  Stop  : kill \$(cat $PIDFILE)%-30s│\n" ""
echo -e "${BOLD}  └─────────────────────────────────────────────────────────┘${NC}"
echo ""
