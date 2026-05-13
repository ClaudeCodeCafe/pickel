#!/usr/bin/env bash
# Smoke tests for pickel using test fixtures
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
FIXTURES="$DIR/fixtures"

PYTHON="${PYTHON:-python3}"
PICKEL="$PYTHON $ROOT/pickel"
export CLAUDE_CONFIG_DIR="$FIXTURES"

echo "=== pickel smoke tests ==="

echo "[1] --version"
$PICKEL --version | grep -q "0.2.0"
echo "  OK"

echo "[2] --help"
$PICKEL --help >/dev/null
echo "  OK"

echo "[3] projects"
OUT=$($PICKEL projects)
echo "$OUT" | grep -q "test-project"
echo "  OK"

echo "[4] projects --json"
$PICKEL projects --json | python3 -m json.tool >/dev/null
echo "  OK"

echo "[5] search"
OUT=$($PICKEL search "smoke")
echo "$OUT" | grep -q "smoke"
echo "  OK"

echo "[6] search --json"
$PICKEL search "smoke" --json | python3 -m json.tool >/dev/null
echo "  OK"

echo "[7] search -r (regex)"
OUT=$($PICKEL search -r "auth|smoke" --max 5)
echo "$OUT" | grep -q "results"
echo "  OK"

echo "[8] search --compact"
OUT=$($PICKEL search "smoke" --compact)
echo "$OUT" | grep -q "project:test-project"
echo "  OK"

echo "[9] chat -p test-project"
OUT=$($PICKEL chat -p test-project)
echo "$OUT" | grep -q "test-project"
echo "  OK"

echo "[10] chat --json"
$PICKEL chat -p test-project --json | python3 -m json.tool >/dev/null
echo "  OK"

echo "[11] errors"
OUT=$($PICKEL errors)
echo "$OUT" | grep -q "issues"
echo "  OK"

echo "[12] errors --json"
$PICKEL errors --json | python3 -m json.tool >/dev/null
echo "  OK"

echo "[13] tools"
OUT=$($PICKEL tools)
echo "$OUT" | grep -q "Bash"
echo "  OK"

echo "[14] tools --json"
$PICKEL tools --json | python3 -m json.tool >/dev/null
echo "  OK"

echo "[15] cost"
OUT=$($PICKEL cost)
echo "$OUT" | grep -q "sonnet"
echo "  OK"

echo "[16] cost --json"
$PICKEL cost --json | python3 -m json.tool >/dev/null
echo "  OK"

echo ""
echo "=== All smoke tests passed ==="
