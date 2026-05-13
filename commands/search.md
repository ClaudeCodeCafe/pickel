---
description: Search across all Claude Code conversation logs
argument-hint: '<query> [-p PROJECT] [--today] [--since YYYY-MM-DD] [-m N]'
allowed-tools: Bash, Read, AskUserQuestion
---

# /pickel:search — Search conversation history

Search for keywords across all past Claude Code sessions.

## Steps

1. Parse the arguments. The first argument(s) are the search query. Optional flags:
   - `-p PROJECT`: filter by project name
   - `--today`: only today's sessions
   - `--since YYYY-MM-DD`: sessions since date
   - `-m N`: max results (default 10)
   - `-r`: use regex search

2. Check pickel is available:

```bash
test -x "${CLAUDE_PLUGIN_ROOT}/pickel" && echo "OK" || echo "MISSING"
```

If missing, tell the user to run `/pickel:setup` and stop.

3. Run the search:

```bash
"${CLAUDE_PLUGIN_ROOT}/pickel" search "$QUERY" --compact $EXTRA_FLAGS
```

4. Present the results clearly. If there are many matches, summarize the recurring themes. If no results, suggest broadening the query or checking the project name.
