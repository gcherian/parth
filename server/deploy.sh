#!/usr/bin/env bash
# deploy.sh — deploy latest Parth server + rebuild and install Flutter app on phone.
#
# Usage:
#   ./deploy.sh              # server + Flutter build + install (if device connected)
#   ./deploy.sh --server     # server restart only
#   ./deploy.sh --app        # Flutter build + install only
#   ./deploy.sh --url        # print current server URLs (no restart)
#
# Phone must be connected via USB (or wirelessly paired in Xcode) for auto-install.
# If no device is detected, the script builds an APK/IPA for manual sideload.

set -euo pipefail

SERVER_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SERVER_DIR/../app" && pwd)"
PORT=8000
PIDFILE="/tmp/parth.pid"
LOG="/tmp/parth_server.log"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓  $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠  $*${NC}"; }
info() { echo -e "${CYAN}  ➜  $*${NC}"; }
die()  { echo -e "${RED}  ✗  $*${NC}"; exit 1; }
hdr()  { echo -e "\n${CYAN}  ── $* ──${NC}"; }

# ── Parse flags ───────────────────────────────────────────────────────────────
DO_SERVER=true
DO_APP=true
case "${1:-}" in
    --server) DO_APP=false ;;
    --app)    DO_SERVER=false ;;
    --url)
        TS_IP=$(tailscale ip -4 2>/dev/null || echo "no-tailscale")
        LOCAL=$(ipconfig getifaddr en0 2>/dev/null || echo "localhost")
        echo ""
        echo "  Parth server URLs:"
        echo "    Local     → http://$LOCAL:$PORT"
        echo "    Tailscale → http://$TS_IP:$PORT"
        echo ""
        exit 0
        ;;
esac

# ── Resolve IPs ───────────────────────────────────────────────────────────────
TS_IP=$(tailscale ip -4 2>/dev/null || echo "")
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "localhost")
SERVER_IP="${TS_IP:-$LOCAL_IP}"
SERVER_URL="http://$SERVER_IP:$PORT"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║         PARTH DEPLOY                     ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
info "Server → $SERVER_URL"
[ -n "$TS_IP" ] && ok "Tailscale up" || warn "Tailscale not running — phone needs same WiFi"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — SERVER
# ══════════════════════════════════════════════════════════════════════════════
if $DO_SERVER; then
    hdr "Server"

    # ── Stop existing server ──────────────────────────────────────────────────
    if [ -f "$PIDFILE" ]; then
        OLD_PID=$(cat "$PIDFILE")
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill "$OLD_PID" 2>/dev/null && ok "Stopped server (pid $OLD_PID)" || true
            sleep 1
        fi
        rm -f "$PIDFILE"
    fi
    # Belt-and-suspenders: kill anything still holding :8000
    STALE=$(lsof -i ":$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
    if [ -n "$STALE" ]; then
        kill "$STALE" 2>/dev/null && warn "Killed stale process $STALE on :$PORT" || true
        sleep 1
    fi
    ok "Port $PORT clear"

    # ── Prerequisites check ───────────────────────────────────────────────────
    # Postgres
    if ! pg_isready -U parth -d parth -q 2>/dev/null; then
        info "Starting Postgres..."
        brew services start postgresql@14 2>/dev/null || true
        for i in {1..15}; do pg_isready -U parth -d parth -q 2>/dev/null && break; sleep 1; done
    fi
    pg_isready -U parth -d parth -q 2>/dev/null && ok "Postgres ready" || die "Postgres not ready"

    # Ollama
    if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        info "Starting Ollama..."
        open -a Ollama 2>/dev/null || ollama serve >>/tmp/ollama.log 2>&1 &
        for i in {1..20}; do curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
    fi
    curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && ok "Ollama ready" || warn "Ollama not responding"

    # ── Apply DB schema (idempotent) ──────────────────────────────────────────
    cd "$SERVER_DIR"
    source venv/bin/activate
    info "Applying DB schema..."
    python3 - <<'PYEOF'
import asyncio, sys
sys.path.insert(0, '.')
from foundation.db import apply_schema
asyncio.run(apply_schema())
PYEOF
    ok "DB schema up to date"

    # ── Sleep prevention ──────────────────────────────────────────────────────
    sudo pmset -c sleep 0 disksleep 0 2>/dev/null && ok "Sleep prevention on" || true

    # ── Start server ──────────────────────────────────────────────────────────
    info "Starting uvicorn..."
    (
        cd "$SERVER_DIR"
        source venv/bin/activate
        while true; do
            uvicorn main:app --host 0.0.0.0 --port "$PORT" --log-level info >> "$LOG" 2>&1
            echo "[$(date)] Server exited — restarting in 5s" >> "$LOG"
            sleep 5
        done
    ) &
    echo $! > "$PIDFILE"

    echo -n "  Waiting for server"
    for i in {1..30}; do
        curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1 && break
        echo -n "."
        sleep 1
    done
    echo ""
    curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1 || die "Server failed to start — check $LOG"
    ok "Server running (pid $(cat $PIDFILE)) — logs: $LOG"
fi

# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — FLUTTER APP
# ══════════════════════════════════════════════════════════════════════════════
if $DO_APP; then
    hdr "Flutter App"
    cd "$APP_DIR"

    # ── Sync server URL into app if it changed ────────────────────────────────
    CHAT_PROVIDER="lib/providers/chat_provider.dart"
    CURRENT_URL=$(grep -oE "http://[0-9.:]+:[0-9]+" "$CHAT_PROVIDER" | head -1 || echo "")
    if [ -n "$CURRENT_URL" ] && [ "$CURRENT_URL" != "$SERVER_URL" ]; then
        sed -i '' "s|${CURRENT_URL}|${SERVER_URL}|g" "$CHAT_PROVIDER"
        ok "Updated server URL: $CURRENT_URL → $SERVER_URL"
    else
        ok "Server URL: $SERVER_URL"
    fi

    # ── Detect connected device ───────────────────────────────────────────────
    # Give Xcode a moment to enumerate wireless devices
    DEVICE_LINE=$(flutter devices 2>/dev/null | grep -E "(iPhone|iPad|android)" | head -1 || true)
    DEVICE_ID=$(echo "$DEVICE_LINE" | grep -oE "• [a-zA-Z0-9_-]+ •" | head -1 | tr -d '• ' || true)
    DEVICE_NAME=$(echo "$DEVICE_LINE" | cut -d'•' -f1 | xargs || true)

    if [ -n "$DEVICE_ID" ]; then
        ok "Device: $DEVICE_NAME ($DEVICE_ID)"
        info "Building in release mode and installing..."
        flutter run --release --device-id "$DEVICE_ID" --dart-define=SERVER_URL="$SERVER_URL"
        ok "App deployed to $DEVICE_NAME"
    else
        warn "No phone detected via USB or wireless pairing."
        echo ""
        echo "  Attempting to build an installable artifact..."
        echo ""

        # ── iOS: build IPA if Xcode is available ─────────────────────────────
        if command -v xcodebuild &>/dev/null; then
            info "Building iOS archive (release)..."
            flutter build ipa \
                --release \
                --dart-define=SERVER_URL="$SERVER_URL" \
                --export-method development 2>&1 || {
                warn "IPA build failed — trying unsigned archive for AirDrop"
                flutter build ios --release --no-codesign \
                    --dart-define=SERVER_URL="$SERVER_URL" 2>&1 || true
            }
            IPA=$(find build/ios/ipa -name "*.ipa" 2>/dev/null | head -1 || true)
            if [ -n "$IPA" ]; then
                ok "IPA ready: $IPA"
                echo ""
                echo "  To install on iPhone:"
                echo "    1. AirDrop the .ipa to your phone"
                echo "    2. Or: ideviceinstaller -i \"$IPA\"  (brew install ideviceinstaller)"
                echo "    3. Or: connect phone → Xcode → Devices → drag .ipa"
            else
                APP=$(find build/ios/Release-iphoneos -name "*.app" 2>/dev/null | head -1 || true)
                [ -n "$APP" ] && ok "Archive: $APP" || warn "Build produced no installable artifact"
                echo ""
                echo "  Connect your iPhone via USB, then re-run:"
                echo "    ./deploy.sh --app"
            fi
        else
            # ── Android fallback ──────────────────────────────────────────────
            info "Building Android APK..."
            flutter build apk --release \
                --dart-define=SERVER_URL="$SERVER_URL"
            APK="build/app/outputs/flutter-apk/app-release.apk"
            ok "APK: $APP_DIR/$APK"
            echo ""
            echo "  To install on Android:"
            echo "    adb install $APP_DIR/$APK"
            echo "  Or transfer the APK and enable 'Install unknown apps' on the phone."
        fi

        echo ""
        echo "  Once installed, the app will connect to:"
        echo "    $SERVER_URL"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo "  ┌──────────────────────────────────────────────┐"
echo "  │  PARTH IS LIVE                               │"
echo "  ├──────────────────────────────────────────────┤"
printf "  │  Server    : %-31s│\n" "$SERVER_URL"
printf "  │  Monitor   : %-31s│\n" "${SERVER_URL}/monitor"
printf "  │  Demo      : %-31s│\n" "${SERVER_URL}/demo"
printf "  │  Logs      : %-31s│\n" "$LOG"
echo "  └──────────────────────────────────────────────┘"
echo ""
