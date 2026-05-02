#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="python3"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         ARIA — Local AI Launcher         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Python check ──────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "✗ Python 3 not found. Install it: sudo apt install python3 python3-pip python3-venv"
  exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Python $PY_VER found"

# ── Virtual environment ────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
PYTHON="$VENV_DIR/bin/python"

# ── Install dependencies ───────────────────────────────────────────────────
echo "→ Checking dependencies..."
pip install -q -r requirements.txt --upgrade

echo "✓ Dependencies ready"

# ── Ollama check ───────────────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
  echo "✓ Ollama found"
  if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "→ Starting Ollama server..."
    ollama serve &>/tmp/ollama.log &
    sleep 2
  else
    echo "✓ Ollama already running"
  fi
else
  echo ""
  echo "⚠  Ollama not found."
  echo "   Install it: curl -fsSL https://ollama.ai/install.sh | sh"
  echo "   Then pull a model: ollama pull llama3.2"
  echo "   The app will still start but AI won't work until Ollama is running."
  echo ""
fi

# ── Data dirs ─────────────────────────────────────────────────────────────
mkdir -p data/knowledge data/uploads data/sessions

# ── Launch ─────────────────────────────────────────────────────────────────
PORT=$(python3 -c "import json; print(json.load(open('config.json')).get('port', 7860))" 2>/dev/null || echo "7860")
echo ""
echo "→ Starting ARIA on http://localhost:$PORT"
echo "  Press Ctrl+C to stop"
echo ""

exec "$PYTHON" app.py
