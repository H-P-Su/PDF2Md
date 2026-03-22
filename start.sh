#!/usr/bin/env bash
# start.sh — start Ollama and Streamlit if not already running, then open browser.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STREAMLIT_PORT=8501
OLLAMA_HOST="http://localhost:11434"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✔ $*${NC}"; }
info() { echo -e "${YELLOW}→ $*${NC}"; }

# ── Ollama ────────────────────────────────────────────────────────────────────
if pgrep -x "ollama" > /dev/null 2>&1; then
    ok "Ollama already running"
else
    info "Starting Ollama..."
    ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
    # Wait up to 10 s for Ollama to become ready
    for i in $(seq 1 10); do
        if curl -s "$OLLAMA_HOST" > /dev/null 2>&1; then
            ok "Ollama started"
            break
        fi
        sleep 1
        if [ "$i" -eq 10 ]; then
            echo "⚠ Ollama did not respond in time — check logs/ollama.log"
        fi
    done
fi

# ── Streamlit ─────────────────────────────────────────────────────────────────
if lsof -ti tcp:"$STREAMLIT_PORT" > /dev/null 2>&1; then
    ok "Streamlit already running on port $STREAMLIT_PORT"
else
    info "Starting Streamlit..."
    cd "$SCRIPT_DIR"
    .venv/bin/streamlit run app.py \
        --server.port "$STREAMLIT_PORT" \
        --server.headless true \
        > "$LOG_DIR/streamlit.log" 2>&1 &
    echo $! > "$SCRIPT_DIR/streamlit.pid"

    # Wait up to 15 s for Streamlit to become ready
    for i in $(seq 1 15); do
        if curl -s "http://localhost:$STREAMLIT_PORT" > /dev/null 2>&1; then
            ok "Streamlit started on port $STREAMLIT_PORT"
            break
        fi
        sleep 1
        if [ "$i" -eq 15 ]; then
            echo "⚠ Streamlit did not respond in time — check logs/streamlit.log"
        fi
    done
fi

# ── Open browser ──────────────────────────────────────────────────────────────
info "Opening http://localhost:$STREAMLIT_PORT ..."
open "http://localhost:$STREAMLIT_PORT"
