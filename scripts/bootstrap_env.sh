#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Load .env IF it exists (robust to spaces and quotes)
DOTENV_PATH="$SKILL_DIR/.env"
if [ -f "$DOTENV_PATH" ]; then
  while IFS='=' read -r key value || [ -n "$key" ]; do
    # Skip comments and empty lines
    if [[ "$key" =~ ^# ]] || [ -z "$key" ]; then
      continue
    fi
    # Strip quotes if they exist
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    
    export "$key=$value"
  done < "$DOTENV_PATH"
fi

BM_MD_DIR="${BM_MD_DIR:-}"

if [ -z "$BM_MD_DIR" ]; then
  echo "Error: BM_MD_DIR is not set."
  echo "Please set it in your environment or create a .env file in the root:"
  echo "  echo \"BM_MD_DIR=/path/to/bm-md\" > \"$DOTENV_PATH\""
  exit 1
fi

echo "[1/5] Checking Python..."
python3 --version

echo "[2/5] Checking Bun..."
if ! command -v bun >/dev/null 2>&1; then
  echo "Bun not found. Install it with:"
  echo "  curl -fsSL https://bun.sh/install | bash"
  exit 1
fi

echo "[3/5] Checking Playwright..."
python3 - <<'PY'
import importlib
import sys
mods = ["playwright", "requests", "dotenv"]
missing = []
for mod in mods:
    try:
        importlib.import_module(mod)
    except Exception:
        missing.append(mod)
if missing:
    print("Missing Python packages:", ", ".join(missing))
    print("Install with: python3 -m pip install playwright requests python-dotenv")
    sys.exit(1)
print("Python packages OK")
PY

echo "[4/5] Checking bm-md..."
if [ ! -d "$BM_MD_DIR" ]; then
  echo "bm-md directory not found: $BM_MD_DIR"
  exit 1
fi

echo "[5/5] Exporting recommended bm-md env..."
export BM_MD_RENDER_URL="${BM_MD_RENDER_URL:-http://localhost:2663/api/markdown/render}"
echo "BM_MD_RENDER_URL=$BM_MD_RENDER_URL"

echo
echo "Bootstrap complete."
echo "Next steps:"
echo "  cd \"$BM_MD_DIR\" && npm run dev"
echo "  python3 \"$SKILL_DIR/scripts/init_wechat_login.py\""
