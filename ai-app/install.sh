#!/usr/bin/env bash
# One-time setup script for ARIA

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        ARIA — First-Time Setup           ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Ollama ──────────────────────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
  echo "→ Installing Ollama..."
  curl -fsSL https://ollama.ai/install.sh | sh
else
  echo "✓ Ollama already installed"
fi

# ── 2. Start Ollama ────────────────────────────────────────────────────────
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "→ Starting Ollama server..."
  ollama serve &>/tmp/ollama.log &
  sleep 3
fi

# ── 3. Pull a model ────────────────────────────────────────────────────────
echo ""
echo "Which model do you want to use?"
echo "  1) llama3.2     (3.8GB — good general purpose)"
echo "  2) mistral      (4.1GB — fast and smart)"
echo "  3) llama3.1:8b  (4.7GB — more capable)"
echo "  4) codellama    (3.8GB — code focused)"
echo "  5) Skip (already have a model)"
echo ""
read -p "Choice [1]: " choice
choice=${choice:-1}

case $choice in
  1) MODEL="llama3.2" ;;
  2) MODEL="mistral" ;;
  3) MODEL="llama3.1:8b" ;;
  4) MODEL="codellama" ;;
  5) MODEL="" ;;
  *) MODEL="llama3.2" ;;
esac

if [ -n "$MODEL" ]; then
  echo "→ Pulling $MODEL..."
  ollama pull "$MODEL"
  # Update config
  python3 -c "
import json, sys
cfg = json.load(open('config.json'))
cfg['default_model'] = '$MODEL'
json.dump(cfg, open('config.json','w'), indent=2)
print('✓ Default model set to $MODEL')
"
fi

# ── 4. Python venv + deps ─────────────────────────────────────────────────
echo ""
echo "→ Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Setup complete! Run ./start.sh         ║"
echo "╚══════════════════════════════════════════╝"
echo ""
