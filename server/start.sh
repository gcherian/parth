#!/bin/bash

LOCAL_IP=$(python3 -c "import socket; s=socket.socket(); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo "localhost")
PORT=8000

# ── Ensure Ollama is running ──────────────────────────────────────────────────
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "  Starting Ollama..."
    ollama serve > /tmp/ollama.log 2>&1 &
    OLLAMA_PID=$!
    echo "  Waiting for Ollama to be ready..."
    for i in {1..15}; do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    echo "  Ollama ready (pid $OLLAMA_PID)"
else
    echo "  Ollama already running ✓"
fi

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "  Run ./setup.sh first!"
    exit 1
fi
source venv/bin/activate

# ── Print banner ──────────────────────────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────┐"
echo "│           PARTH AI SERVER  🇮🇳                   │"
echo "├─────────────────────────────────────────────────┤"
echo "│  Model   : gemma3:12b (fallback: llama3.2)      │"
echo "│  Local   : http://localhost:$PORT                  │"
echo "│  Network : http://$LOCAL_IP:$PORT           │"
echo "│  Docs    : http://$LOCAL_IP:$PORT/docs       │"
echo "├─────────────────────────────────────────────────┤"
echo "│  Enter this IP in the Parth app: $LOCAL_IP  │"
echo "└─────────────────────────────────────────────────┘"
echo ""

# ── Start FastAPI ─────────────────────────────────────────────────────────────
uvicorn main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --log-level info
