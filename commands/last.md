---
description: Show the last session summary for a project
argument-hint: '[project-name]'
allowed-tools: Bash, AskUserQuestion
---

# /pickel:last — Show last session

Show a summary of the most recent conversation session for a project.

## Steps

1. Parse the argument. The first argument is the project name (optional).

2. Check pickel is available:

```bash
test -x "${CLAUDE_PLUGIN_ROOT}/pickel" && echo "OK" || echo "MISSING"
```

If missing, tell the user to run `/pickel:setup` and stop.

3. If no project given, list projects first:

```bash
"${CLAUDE_PLUGIN_ROOT}/pickel" projects
```

Then ask the user which project to show using `AskUserQuestion`.

4. Show the last session:

```bash
"${CLAUDE_PLUGIN_ROOT}/pickel" last "$PROJECT"
```

5. Summarize what was worked on in the last session in 2-3 sentences.
