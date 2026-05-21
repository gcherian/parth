#!/bin/bash
set -e

LOCAL_IP=$(python3 -c "import socket; s=socket.socket(); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo "localhost")
PORT=8000
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Docker services (Postgres + MinIO) ───────────────────────────────────────
if command -v docker &> /dev/null && [ -f "docker-compose.yml" ]; then
    if docker compose ps --status running 2>/dev/null | grep -q "postgres"; then
        echo "  Postgres already running ✓"
    else
        echo "  Starting Docker services (Postgres + MinIO)..."
        docker compose up -d
        echo -n "  Waiting for Postgres"
        for i in {1..30}; do
            if docker compose exec -T postgres pg_isready -U parth -q 2>/dev/null; then
                echo " ✓"
                break
            fi
            echo -n "."
            sleep 1
        done
    fi
else
    echo "  Docker not found or no docker-compose.yml — skipping"
fi

# ── Ollama ────────────────────────────────────────────────────────────────────
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "  Starting Ollama..."
    ollama serve > /tmp/ollama.log 2>&1 &
    OLLAMA_PID=$!
    for i in {1..15}; do
        curl -s http://localhost:11434/api/tags > /dev/null 2>&1 && break
        sleep 1
    done
    echo "  Ollama ready (pid $OLLAMA_PID) ✓"
else
    echo "  Ollama already running ✓"
fi

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "  Run ./setup.sh first!"
    exit 1
fi
source venv/bin/activate

# ── Sleep prevention ──────────────────────────────────────────────────────────
sudo pmset -c sleep 0 disksleep 0 2>/dev/null && \
    echo "  Sleep prevention: on" || \
    echo "  Note: run as sudo to prevent sleep"

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────┐"
echo "│             PARTH AI SERVER  🇮🇳                     │"
echo "├─────────────────────────────────────────────────────┤"
echo "│  Chat    : http://$LOCAL_IP:$PORT/chat          │"
echo "│  Monitor : http://$LOCAL_IP:$PORT/monitor       │"
echo "│  Docs    : http://$LOCAL_IP:$PORT/docs          │"
echo "│  Graph   : http://$LOCAL_IP:$PORT/graph         │"
echo "├─────────────────────────────────────────────────────┤"
echo "│  App IP  : $LOCAL_IP:$PORT                  │"
echo "└─────────────────────────────────────────────────────┘"
echo ""

# ── Start FastAPI with auto-restart on crash ──────────────────────────────────
echo "  Starting server (auto-restarts on crash)..."
while true; do
    uvicorn main:app \
        --host 0.0.0.0 \
        --port $PORT \
        --log-level info
    EXIT=$?
    echo ""
    echo "  !! Server exited with code $EXIT at $(date). Restarting in 5s..."
    sleep 5
done
