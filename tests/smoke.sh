#!/usr/bin/env bash
# Smoke tests for pickel using test fixtures
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
FIXTURES="$DIR/fixtures"

PYTHON="${PYTHON:-python3}"

# Allow PICKEL env var to override the command (e.g. PICKEL=pickel for installed package)
if [ -n "${PICKEL:-}" ]; then
  PICKEL_CMD=("$PICKEL")
else
  PICKEL_CMD=("$PYTHON" "$ROOT/pickel")
fi

export CLAUDE_CONFIG_DIR="$FIXTURES"

echo "=== pickel smoke tests ==="

# ── Basic ────────────────────────────────────────────────────────

echo "[1] --version"
"${PICKEL_CMD[@]}" --version | grep -q "0.3.2"
echo "  OK"

echo "[2] --help"
"${PICKEL_CMD[@]}" --help >/dev/null
echo "  OK"

# ── Projects ─────────────────────────────────────────────────────

echo "[3] projects"
OUT=$("${PICKEL_CMD[@]}" projects)
echo "$OUT" | grep -q "test-project"
echo "  OK"

echo "[4] projects --json (field check)"
JSON=$("${PICKEL_CMD[@]}" projects --json)
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
OUT=$("${PICKEL_CMD[@]}" search "smoke")
echo "$OUT" | grep -q "smoke"
echo "  OK"

echo "[7] search --json (field check)"
JSON=$("${PICKEL_CMD[@]}" search "smoke" --json)
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
OUT=$("${PICKEL_CMD[@]}" search -r "auth|smoke" --max 5)
echo "$OUT" | grep -q "results"
echo "  OK"

echo "[9] search --compact"
OUT=$("${PICKEL_CMD[@]}" search "smoke" --compact)
echo "$OUT" | grep -q "project:test-project"
echo "  OK"

echo "[10] search in hyphenated project"
OUT=$("${PICKEL_CMD[@]}" search "deploy" -p my-cool-app)
echo "$OUT" | grep -q "deploy"
echo "  OK"

# ── Chat ─────────────────────────────────────────────────────────

echo "[11] chat -p test-project"
OUT=$("${PICKEL_CMD[@]}" chat -p test-project)
echo "$OUT" | grep -q "test-project"
echo "  OK"

echo "[12] chat --json (field check)"
JSON=$("${PICKEL_CMD[@]}" chat -p test-project --json)
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

# ── Context ─────────────────────────────────────────────────────

echo "[13] context"
OUT=$("${PICKEL_CMD[@]}" context session1 -p test-project)
echo "$OUT" | grep -q "User messages"
echo "  OK"

echo "[14] context --json (field check)"
JSON=$("${PICKEL_CMD[@]}" context session1 -p test-project --json)
"$PYTHON" -c "
import json, sys
data = json.loads(sys.stdin.read())
for key in ('project', 'session', 'user_messages', 'tools_used'):
    assert key in data, f'missing key: {key}'
" <<< "$JSON"
echo "  OK"

# ── Last ────────────────────────────────────────────────────────

echo "[15] last"
OUT=$("${PICKEL_CMD[@]}" last test-project)
echo "$OUT" | grep -q "test-project"
echo "  OK"

echo "[16] last --json (field check)"
JSON=$("${PICKEL_CMD[@]}" last test-project --json)
"$PYTHON" -c "
import json, sys
data = json.loads(sys.stdin.read())
for key in ('project', 'session', 'age', 'model', 'turns', 'tokens', 'last_user', 'last_assistant'):
    assert key in data, f'missing key: {key}'
" <<< "$JSON"
echo "  OK"

# ── Errors ───────────────────────────────────────────────────────

echo "[17] errors"
OUT=$("${PICKEL_CMD[@]}" errors)
echo "$OUT" | grep -q "issues"
echo "  OK"

echo "[18] errors --json"
"${PICKEL_CMD[@]}" errors --json | "$PYTHON" -m json.tool >/dev/null
echo "  OK"

# ── Tools ────────────────────────────────────────────────────────

echo "[19] tools"
OUT=$("${PICKEL_CMD[@]}" tools)
echo "$OUT" | grep -q "Bash"
echo "  OK"

echo "[20] tools --json (field check)"
JSON=$("${PICKEL_CMD[@]}" tools --json)
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

echo "[21] cost"
OUT=$("${PICKEL_CMD[@]}" cost)
echo "$OUT" | grep -q "sonnet"
echo "  OK"

echo "[22] cost --json (field check)"
JSON=$("${PICKEL_CMD[@]}" cost --json)
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

echo "[23] invalid regex exits with error"
if "${PICKEL_CMD[@]}" search -r "[invalid" 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[24] non-existent project"
if "${PICKEL_CMD[@]}" last "nonexistent-project-xyz" 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[25] invalid --since date"
if "${PICKEL_CMD[@]}" search "test" --since "not-a-date" 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[26] --max 0 rejected"
if "${PICKEL_CMD[@]}" search "test" --max 0 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[27] --max -1 rejected"
if "${PICKEL_CMD[@]}" search "test" --max -1 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[28] chat --last 0 rejected"
if "${PICKEL_CMD[@]}" chat -p test-project --last 0 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[29] --quiet suppresses warnings"
"${PICKEL_CMD[@]}" -q projects >/dev/null 2>&1
echo "  OK"

echo "[30] search -p with non-existent project exits 1"
if "${PICKEL_CMD[@]}" search "test" -p "nonexistent-xyz" 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

# ── chat session -p PROJECT ─────────────────────────────────────

echo "[31] chat session1 -p test-project --json"
JSON=$("${PICKEL_CMD[@]}" chat session1 -p test-project --json)
"$PYTHON" -c "
import json, sys
data = json.loads(sys.stdin.read())
assert isinstance(data, list), 'expected list'
assert len(data) > 0, 'expected at least one conversation'
assert data[0]['project'] == 'test-project', f'wrong project: {data[0][\"project\"]}'
" <<< "$JSON"
echo "  OK"

# ── Non-existent project for errors/tools/cost ─────────────────

echo "[32] errors -p non-existent project exits 1"
if "${PICKEL_CMD[@]}" errors -p "nonexistent-xyz" 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[33] tools -p non-existent project exits 1"
if "${PICKEL_CMD[@]}" tools -p "nonexistent-xyz" 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

echo "[34] cost -p non-existent project exits 1"
if "${PICKEL_CMD[@]}" cost -p "nonexistent-xyz" 2>/dev/null; then
  echo "  FAIL (should have exited non-zero)"
  exit 1
else
  echo "  OK"
fi

# ── Malformed JSONL ─────────────────────────────────────────────

echo "[35] malformed JSONL does not crash"
MALFORMED_DIR=$(mktemp -d)
trap 'rm -rf "$MALFORMED_DIR"' EXIT
MALFORMED_PROJ="$MALFORMED_DIR/projects/test-malformed"
mkdir -p "$MALFORMED_PROJ"
printf '{"type":"user","timestamp":"2025-01-01T00:00:00Z","message":{"role":"user","content":"hello"}}\n' > "$MALFORMED_PROJ/bad.jsonl"
printf 'THIS IS NOT JSON\n' >> "$MALFORMED_PROJ/bad.jsonl"
printf '["array","not","object"]\n' >> "$MALFORMED_PROJ/bad.jsonl"
printf '"just a string"\n' >> "$MALFORMED_PROJ/bad.jsonl"
printf '{"type":"assistant","timestamp":"2025-01-01T00:00:05Z","message":{"role":"assistant","model":"claude-sonnet-4-20250514","content":[{"type":"text","text":"hi"}],"usage":{"input_tokens":100,"output_tokens":50}}}\n' >> "$MALFORMED_PROJ/bad.jsonl"
# Should warn but not crash (point CLAUDE_CONFIG_DIR at mktemp so malformed project is visible)
EXIT_CODE=0
OUT=$(CLAUDE_CONFIG_DIR="$MALFORMED_DIR" "${PICKEL_CMD[@]}" search "hello" 2>&1) || EXIT_CODE=$?
if [ "$EXIT_CODE" -ne 0 ]; then
  echo "  FAIL: expected exit 0, got $EXIT_CODE"
  exit 1
fi
echo "$OUT" | grep -q "invalid JSON\|expected object\|hello"
echo "  OK"

echo ""
echo "=== All smoke tests passed ==="
