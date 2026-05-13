---
description: Estimate token costs by model from conversation logs
argument-hint: '[--month] [--today] [-p PROJECT]'
allowed-tools: Bash, AskUserQuestion
---

# /pickel:cost — Token cost estimate

Estimate token usage and costs from Claude Code conversation logs.

## Steps

1. Parse the arguments. Optional flags:
   - `--month`: this month's usage
   - `--today`: today's usage
   - `-p PROJECT`: filter by project

2. Check pickel is available:

```bash
test -x "${CLAUDE_PLUGIN_ROOT}/pickel" && echo "OK" || echo "MISSING"
```

If missing, tell the user to run `/pickel:setup` and stop.

3. Run the cost command:

```bash
"${CLAUDE_PLUGIN_ROOT}/pickel" cost $FLAGS
```

4. Present the cost breakdown by model. Note that these are estimates based on token counts recorded in the logs — actual billed amounts may differ.
