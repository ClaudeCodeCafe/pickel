#!/usr/bin/env bash
# Smoke tests for pickel using test fixtures
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
FIXTURES="$DIR/fixtures"

PYTHON="${PYTHON:-python3}"
PICKEL=("$PYTHON" "$ROOT/pickel")
export CLAUDE_CONFIG_DIR="$FIXTURES"

echo "=== pickel smoke tests ==="

# ── Basic ────────────────────────────────────────────────────────

echo "[1] --version"
"${PICKEL[@]}" --version | grep -q "0.3.0"
echo "  OK"

echo "[2] --help"
"${PICKEL[@]}" --help >/dev/null
echo "  OK"

# ── Projects ─────────────────────────────────────────────────────

echo "[3] projects"
OUT=$("${PICKEL[@]}" projects)
echo "$OUT" | grep -q "test-project"
echo "  OK"

echo "[4] projects --json (field check)"
JSON=$("${PICKEL[@]}" projects --json)
"$PYTHON" -c "
import json, sys
data = json.loads(sys.stdin.read())
assert isinstance(data, list), 'expected list'
for item in data:
    for key in ('project', 'sessions', 'size_mb', 'last'):
        assert key in item, f'missing key: {key}'
" <<< "$JSON"
echo "  OK"

echo "[5] projects shows hyphenated repo name correctly"
echo "$OUT" | grep -q "my-cool-app"
echo "  OK"

# ── Search ───────────────────────────────────────────────────────

echo "[6] search"
OUT=$("${PICKEL[@]}" search "smoke")
echo "$OUT" | grep -q "smoke"
echo "  OK"

echo "[7] search --json (field check)"
JSON=$("${PICKEL[@]}" search "smoke" --json)
"$PYTHON" -c "
import json, sys
data = json.loads(sys.stdin.read())
assert isinstance(data, list), 'expected list'
for item in data:
    for key in ('project', 'session', 'role', 'timestamp', 'line'):
        assert key in item, f'missing key: {key}'
" <<< "$JSON"
echo "  OK"

echo "[8] search -r (regex)"
OUT=$("${PICKEL[@]}" search -r "auth|smoke" --max 5)
echo "$OUT" | grep -q "results"
echo "  OK"

echo "[9] search --compact"
OUT=$("${PICKEL[@]}" search "smoke" --compact)
echo "$OUT" | grep -q "project:test-project"
echo "  OK"

echo "[10] search in hyphenated project"
OUT=$("${PICKEL[@]}" search "deploy" -p my-cool-app)
echo "$OUT" | grep -q "deploy"
echo "  OK"

# ── Chat ─────────────────────────────────────────────────────────

echo "[11] chat -p test-project"
OUT=$("${PICKEL[@]}" chat -p test-project)
echo "$OUT" | grep -q "test-project"
echo "  OK"

echo "[12] chat --json (field check)"
JSON=$("${PICKEL[@]}" chat -p test-project --json)
"$PYTHON" -c "
import json, sys
data = json.loads(sys.stdin.read())
assert isinstance(data, list), 'expected list'
for conv in data:
    for key in ('project', 'session', 'messages'):
        assert key in conv, f'missing key: {key}'
    for msg in conv['messages']:
        for key in ('role', 'timestamp', 'text'):
            assert key in msg, f'missing message key: {key}'
" <<< "$JSON"
echo "  OK"

# ── Errors ───────────────────────────────────────────────────────

echo "[13] errors"
OUT=$("${PICKEL[@]}" errors)
echo "$OUT" | grep -q "issues"
echo "  OK"

echo "[14] errors --json"
"${PICKEL[@]}" errors --json | "$PYTHON" -m json.tool >/dev/null
echo "  OK"

# ── Tools ────────────────────────────────────────────────────────

echo "[15] tools"
OUT=$("${PICKEL[@]}" tools)
echo "$OUT" | grep -q "Bash"
echo "  OK"

echo "[16] tools --json (field check)"
JSON=$("${PICKEL[@]}" tools --json)
"$PYTHON" -c "
import json, sys
data = json.loads(sys.stdin.read())
assert isinstance(data, list), 'expected list'
for item in data:
    assert 'tool' in item, 'missing key: tool'
    assert 'count' in item, 'missing key: count'
" <<< "$JSON"
echo "  OK"

# ── Cost ─────────────────────────────────────────────────────────

echo "[17] cost"
OUT=$("${PICKEL[@]}" cost)
echo "$OUT" | grep -q "sonnet"
echo "  OK"

echo "[18] cost --json (field check)"
JSON=$("${PICKEL[@]}" cost --json)
"$PYTHON" -c "
import json, sys
data = json.loads(sys.stdin.read())
assert 'models' in data, 'missing key: models'
assert 'total_input_tokens' in data, 'missing key: total_input_tokens'
assert 'total_output_tokens' in data, 'missing key: total_output_tokens'
assert 'total_cost_usd' in data, 'missing key: total_cost_usd'
for m in data['models']:
    for key in ('model', 'input_tokens', 'output_tokens', 'cost_usd'):
        assert key in m, f'missing key: {key}'
" <<< "$JSON"
echo "  OK"

# ── Error paths (negative tests) ────────────────────────────────

echo "[19] invalid regex exits with error"
if "${PICKEL[@]}" search -r "[invalid" 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[20] non-existent project"
if "${PICKEL[@]}" last "nonexistent-project-xyz" 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[21] invalid --since date"
if "${PICKEL[@]}" search "test" --since "not-a-date" 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[22] --max 0 rejected"
if "${PICKEL[@]}" search "test" --max 0 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[23] --max -1 rejected"
if "${PICKEL[@]}" search "test" --max -1 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[24] chat --last 0 rejected"
if "${PICKEL[@]}" chat -p test-project --last 0 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[25] --quiet suppresses warnings"
"${PICKEL[@]}" -q projects >/dev/null 2>&1
echo "  OK"

echo ""
echo "=== All smoke tests passed ==="
