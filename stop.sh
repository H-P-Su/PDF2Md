#!/usr/bin/env bash
# stop.sh — stop Streamlit and Ollama servers.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✔ $*${NC}"; }
gone() { echo -e "${RED}✘ $*${NC}"; }

# ── Streamlit ─────────────────────────────────────────────────────────────────
PID_FILE="$SCRIPT_DIR/streamlit.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && ok "Streamlit stopped (pid $PID)"
    else
        gone "Streamlit pid $PID not found"
    fi
    rm -f "$PID_FILE"
else
    # Fall back to port-based kill
    PIDS=$(lsof -ti tcp:8501 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "$PIDS" | xargs kill && ok "Streamlit stopped"
    else
        gone "Streamlit was not running"
    fi
fi

# ── Ollama ────────────────────────────────────────────────────────────────────
PIDS=$(pgrep -x "ollama" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs kill && ok "Ollama stopped"
else
    gone "Ollama was not running"
fi
