#!/usr/bin/env bash
# package.sh — create a clean deployment zip of PDF2Md source files.
#
# Excludes all local state:
#   storage/   — papers, database, voice models
#   .venv/     — virtual environment
#   .claude/   — local Claude Code settings
#   __pycache__ / *.pyc — compiled bytecode
#
# Usage:
#   ./package.sh              # creates pdf2md-YYYYMMDD-HHMMSS.zip
#   ./package.sh myname.zip   # creates myname.zip

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUTPUT="${1:-pdf2md-${TIMESTAMP}.zip}"

# Resolve to absolute path so the zip lands in the project root
# regardless of where the script is called from
if [[ "$OUTPUT" != /* ]]; then
    OUTPUT="${SCRIPT_DIR}/${OUTPUT}"
fi

cd "$SCRIPT_DIR"

echo "Building deployment package..."

zip -r "$OUTPUT" . \
    --exclude "*.zip" \
    --exclude "./.venv/*" \
    --exclude "./.claude/*" \
    --exclude "./storage/*" \
    --exclude "./__pycache__/*" \
    --exclude "./services/__pycache__/*" \
    --exclude "./*.pyc" \
    --exclude "./services/*.pyc" \
    --exclude "./.git/*" \
    --exclude "./=*" \
    --exclude "./logs/*" \
    --exclude "./streamlit.pid"

echo ""
echo "Created: $OUTPUT"
echo "Size:    $(du -sh "$OUTPUT" | cut -f1)"
echo ""
echo "Included files:"
zip -sf "$OUTPUT" | grep -v '/$' | sort | sed 's|^\s*||'
