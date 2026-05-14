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

# Isolate ores directory so tests don't touch real ~/.pickel/ores
ORES_TMPDIR=$(mktemp -d)
export PICKEL_ORES_DIR="$ORES_TMPDIR"

fail() {
    echo "  FAIL: $1"
    exit 1
}

check_exit_code() {
    local actual=$1
    local expected=$2
    local label=$3
    if [ "$actual" -ne "$expected" ]; then
        fail "$label (expected exit $expected, got $actual)"
    fi
    echo "  OK"
}

echo "=== pickel smoke tests ==="

# ── Basic ────────────────────────────────────────────────────────

echo "[1] --version"
"${PICKEL_CMD[@]}" --version | grep -q "0.6.1"
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
trap 'rm -rf "$MALFORMED_DIR" "$ORES_TMPDIR"' EXIT
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

# ── Mine ─────────────────────────────────────────────────────────

echo "[36] mine --dry-run (empty stdin)"
echo '{}' | "${PICKEL_CMD[@]}" mine --dry-run >/dev/null
echo "  OK"

echo "[37] mine --json (empty stdin)"
JSON=$(echo '{}' | "${PICKEL_CMD[@]}" mine --json)
"$PYTHON" -c "
import json, sys
data = json.loads(sys.stdin.read())
for key in ('decisions', 'discoveries', 'errors_fixes', 'unfinished'):
    assert key in data, f'missing key: {key}'
    assert isinstance(data[key], list), f'{key} should be list'
" <<< "$JSON"
echo "  OK"

echo "[38] mine CLI mode outputs plain text (not JSON hookSpecificOutput)"
OUT=$(echo '{}' | "${PICKEL_CMD[@]}" mine)
echo "$OUT" | grep -q "hookSpecificOutput" && fail "[38] CLI mode should not output hookSpecificOutput" || true
echo "  OK"

# [39] mine with invalid JSON stdin
echo "[39] mine with invalid JSON stdin"
EC=0
echo 'not json' | "${PICKEL_CMD[@]}" mine 2>/dev/null || EC=$?
check_exit_code "$EC" 0 "[39] mine with invalid stdin returns 0"

# [40] mine with array stdin (not object)
echo "[40] mine with array stdin"
EC=0
echo '[]' | "${PICKEL_CMD[@]}" mine 2>/dev/null || EC=$?
check_exit_code "$EC" 0 "[40] mine with array stdin returns 0"

# [41] mine --transcript with missing file
echo "[41] mine --transcript with missing file"
EC=0
"${PICKEL_CMD[@]}" mine --transcript /nonexistent/path.jsonl 2>/dev/null || EC=$?
check_exit_code "$EC" 1 "[41] mine --transcript missing file exits 1"

# [42] mine hook mode saves .last-mine-unknown.md
echo "[42] mine hook mode saves .last-mine-unknown.md"
rm -f "$ORES_TMPDIR/.last-mine-unknown.md"
echo '{"hook_event_name": "PreCompact"}' | "${PICKEL_CMD[@]}" mine 2>/dev/null
[ -f "$ORES_TMPDIR/.last-mine-unknown.md" ] || fail "[42] mine should save .last-mine-unknown.md in hook mode"
echo "  OK"

# [43] mine --post removed (should fail)
echo "[43] mine --post should not exist"
EC=0
"${PICKEL_CMD[@]}" mine --post 2>/dev/null || EC=$?
check_exit_code "$EC" 2 "[43] mine --post should not exist"

# ── Wrap / Recall / Ores ─────────────────────────────────────────

# [44] wrap saves an ore
echo "[44] wrap saves an ore"
echo '{"transcript_path": "'"$FIXTURES"'/projects/test-project/session1.jsonl", "session_id": "test123", "cwd": "/Users/test/.ghq/github.com/testorg/test-project"}' | "${PICKEL_CMD[@]}" wrap
check_exit_code $? 0 "[44] wrap exits 0"

# [45] ores list shows saved ore
echo "[45] ores list shows saved ore"
OUT=$("${PICKEL_CMD[@]}" ores)
echo "$OUT" | grep -q "test" || fail "[45] ores list should show project"
echo "  OK"

# [46] ores show displays content
echo "[46] ores show displays content"
OUT=$("${PICKEL_CMD[@]}" ores show)
echo "$OUT" | grep -q "Ore" || echo "$OUT" | grep -q "ore" || fail "[46] ores show should display ore"
echo "  OK"

# [47] ores --json
echo "[47] ores --json"
JSON=$("${PICKEL_CMD[@]}" ores --json)
echo "$JSON" | "$PYTHON" -c "import json,sys; d=json.loads(sys.stdin.read()); assert len(d['projects']) > 0" || fail "[47] ores json should have projects"
echo "  OK"

# [48] recall loads previous ore
echo "[48] recall loads previous ore"
OUT=$(echo '{"cwd": "/Users/test/.ghq/github.com/testorg/test-project", "source": "startup"}' | "${PICKEL_CMD[@]}" recall)
[ -n "$OUT" ] || fail "[48] recall should output something"
echo "  OK"

# [49] wrap with empty stdin exits 0
echo "[49] wrap with empty stdin exits 0"
EC=0
echo '{}' | "${PICKEL_CMD[@]}" wrap 2>/dev/null || EC=$?
check_exit_code "$EC" 0 "[49] wrap with empty stdin exits 0"

# [50] recall with empty stdin exits 0
echo "[50] recall with empty stdin exits 0"
EC=0
echo '{}' | "${PICKEL_CMD[@]}" recall 2>/dev/null || EC=$?
check_exit_code "$EC" 0 "[50] recall with empty stdin exits 0"

# ── mine → recall pipeline ────────────────────────────────────────

# [51] mine hook mode: empty stdout, .last-mine-s1.md created
echo "[51] mine hook mode: empty stdout, .last-mine-s1.md created"
rm -f "$ORES_TMPDIR/.last-mine-s1.md"
OUT=$(echo '{"hook_event_name": "PreCompact", "transcript_path": "'"$FIXTURES"'/projects/test-project/session1.jsonl", "session_id": "s1", "cwd": "/x/y/test-project"}' | "${PICKEL_CMD[@]}" mine 2>/dev/null)
[ -z "$OUT" ] || fail "[51] mine hook mode should output nothing to stdout"
[ -f "$ORES_TMPDIR/.last-mine-s1.md" ] || fail "[51] mine should save .last-mine-s1.md"
echo "  OK"

# [52] recall compact source reads .last-mine-unknown.md
echo "[52] recall compact source reads .last-mine-unknown.md"
printf '# Rescued Context\nsome important note\n' > "$ORES_TMPDIR/.last-mine-unknown.md"
OUT=$(echo '{"source": "compact"}' | "${PICKEL_CMD[@]}" recall)
echo "$OUT" | grep -q "Rescued Context" || fail "[52] recall should output .last-mine-unknown.md content"
echo "  OK"

# [53] mine → recall pipeline: .last-mine-unknown.md deleted after recall
echo "[53] mine → recall pipeline: .last-mine-unknown.md deleted after recall"
rm -f "$ORES_TMPDIR/.last-mine-unknown.md"
echo '{"hook_event_name": "PreCompact"}' | "${PICKEL_CMD[@]}" mine 2>/dev/null
[ -f "$ORES_TMPDIR/.last-mine-unknown.md" ] || fail "[53] mine should create .last-mine-unknown.md"
echo '{"source": "compact"}' | "${PICKEL_CMD[@]}" recall 2>/dev/null
[ ! -f "$ORES_TMPDIR/.last-mine-unknown.md" ] || fail "[53] recall should delete .last-mine-unknown.md after reading"
echo "  OK"

# [54] noise filter: skip patterns excluded from extraction
echo "[54] noise filter: skip patterns excluded from extraction"
NOISE_FILE=$(mktemp /tmp/pickel-noise-XXXX.jsonl)
printf '{"type":"user","timestamp":"2025-01-01T00:00:01Z","message":{"role":"user","content":"Exit code 1"}}\n' > "$NOISE_FILE"
printf '{"type":"user","timestamp":"2025-01-01T00:00:02Z","message":{"role":"user","content":"This session is being continued from a previous conversation due to length."}}\n' >> "$NOISE_FILE"
printf '{"type":"assistant","timestamp":"2025-01-01T00:00:03Z","message":{"role":"assistant","model":"claude-sonnet-4-20250514","content":[{"type":"text","text":"把握しました。進めます。"}],"usage":{"input_tokens":10,"output_tokens":5}}}\n' >> "$NOISE_FILE"
JSON=$("${PICKEL_CMD[@]}" mine --json --transcript "$NOISE_FILE")
"$PYTHON" -c "
import json, sys
data = json.loads(sys.stdin.read())
all_items = data['decisions'] + data['discoveries'] + data['errors_fixes'] + data['unfinished']
for item in all_items:
    assert 'Exit code' not in item, f'noise found: {item}'
    assert 'This session is being continued' not in item, f'noise found: {item}'
    assert '把握しました' not in item, f'noise found: {item}'
" <<< "$JSON" || fail "[54] noise items should not appear in extracted output"
rm -f "$NOISE_FILE"
echo "  OK"

# [55] E2E pipeline: mine with session_id → recall → file deleted
echo "[55] E2E pipeline: mine with session_id → recall → file deleted"
E2E_SID="e2esid"
rm -f "$ORES_TMPDIR/.last-mine-${E2E_SID}.md"
echo '{"hook_event_name": "PreCompact", "transcript_path": "'"$FIXTURES"'/projects/test-project/session1.jsonl", "session_id": "'"$E2E_SID"'", "cwd": "/x/y/test-project"}' | "${PICKEL_CMD[@]}" mine 2>/dev/null
[ -f "$ORES_TMPDIR/.last-mine-${E2E_SID}.md" ] || fail "[55] mine should create .last-mine-${E2E_SID}.md"
OUT=$(echo '{"source": "compact", "session_id": "'"$E2E_SID"'"}' | "${PICKEL_CMD[@]}" recall 2>/dev/null)
[ -n "$OUT" ] || fail "[55] recall should output meaningful content"
[ ! -f "$ORES_TMPDIR/.last-mine-${E2E_SID}.md" ] || fail "[55] recall should delete .last-mine-${E2E_SID}.md"
echo "  OK"

echo ""
echo "=== All smoke tests passed ==="
