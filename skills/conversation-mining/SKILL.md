---
name: conversation-mining
description: >
  Search past Claude Code sessions when the user asks about previous work, past solutions,
  or what was built before. Triggers on questions like "what did I work on recently?",
  "did we solve this before?", "what did I build last week?", "show me past sessions",
  "前のセッションで何やった？", "この問題前に解決した？", "先週何を作った？",
  or any reference to prior conversation history.
---

# Conversation Mining with pickel

When the user asks about past sessions, previous work, or prior solutions:

## Steps

1. Understand what the user is looking for:
   - A specific topic or keyword → use `search`
   - What they last worked on in a project → use `last`
   - Overview of all projects → use `projects`
   - Token costs → use `cost`

2. Run the appropriate pickel command:

**Search for a topic:**
```bash
"${CLAUDE_PLUGIN_ROOT}/pickel" search "<keywords>" --compact
```

**Show last session for a project:**
```bash
"${CLAUDE_PLUGIN_ROOT}/pickel" last <project>
```

**List all projects:**
```bash
"${CLAUDE_PLUGIN_ROOT}/pickel" projects
```

**Today's sessions only:**
```bash
"${CLAUDE_PLUGIN_ROOT}/pickel" search "<keywords>" --today --compact
```

**Since a specific date:**
```bash
"${CLAUDE_PLUGIN_ROOT}/pickel" search "<keywords>" --since YYYY-MM-DD --compact
```

3. Present the results to the user in a clear, readable format.

## Trigger examples

- "前のセッションで何やった？" → `last <current-project>`
- "この問題前に解決した？" → `search "<problem keyword>" --compact`
- "先週何を作った？" → `search "" --since <last-week-date> --compact`
- "最近のプロジェクト一覧" → `projects`
- "authのバグ、前に直したっけ？" → `search "auth" --compact`
- "what did I work on yesterday?" → `search "" --since <yesterday-date> --compact`
- "have we implemented X before?" → `search "X" --compact`

## Important

- If pickel is not available at `${CLAUDE_PLUGIN_ROOT}/pickel`, tell the user to run `/pickel:setup`
- Use `--compact` for search to keep output readable in chat
- For project names, pass a partial name — pickel will match on substrings
- pickel reads from `~/.claude/projects/` and never sends data over the network
