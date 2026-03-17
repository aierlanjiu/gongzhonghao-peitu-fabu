#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BM_MD_DIR="/Users/papazed/00_Publiac Account/02_排版tools/bm-md"

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
