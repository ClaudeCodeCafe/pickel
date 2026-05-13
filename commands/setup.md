---
description: Check pickel CLI availability and Python version
allowed-tools: Bash, AskUserQuestion
---

# /pickel:setup — Dependency check

Check whether pickel is available and working.

Run these checks:

```bash
echo "=== pickel setup check ==="
echo ""

if [ -x "${CLAUDE_PLUGIN_ROOT}/pickel" ]; then
  VER=$(python3 "${CLAUDE_PLUGIN_ROOT}/pickel" --version 2>&1)
  echo "✅ pickel     $VER   ready"
else
  echo "❌ pickel     not found at ${CLAUDE_PLUGIN_ROOT}/pickel"
fi

PY_VER=$(python3 --version 2>&1)
echo "✅ python     $PY_VER"

if [ -d "${HOME}/.claude/projects" ]; then
  COUNT=$(ls "${HOME}/.claude/projects" | wc -l | tr -d ' ')
  echo "✅ logs       ~/.claude/projects ($COUNT projects)"
else
  echo "❌ logs       ~/.claude/projects not found"
fi

echo ""
```

Present the results to the user.

If pickel is not found, say:

```
pickel CLI が見つかりません。プラグインが正しくインストールされているか確認してください。
${CLAUDE_PLUGIN_ROOT}/pickel が存在することを確認してください。
```

If everything is fine, say:

```
All good! Use /pickel:search to mine your conversation history.
```
