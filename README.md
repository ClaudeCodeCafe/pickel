# ⛏️ pickel

A pickaxe for mining Claude Code conversation logs.

One command to search all your Claude Code conversations.

## Install

```bash
# Homebrew
brew install ClaudeCodeCafe/tap/pickel

# pip
pip install pickel-cli

# or just download
curl -fsSL https://raw.githubusercontent.com/ClaudeCodeCafe/pickel/master/pickel -o /usr/local/bin/pickel
chmod +x /usr/local/bin/pickel
```

## Usage

```bash
# Search across all conversations
pickel search "auth middleware"

# Filter by project
pickel search "migration" -p my-app

# List all projects
pickel projects

# Last session summary
pickel last my-app

# Session context
pickel context a1b2c3d4
```

## Commands

### `pickel search <query>`

Full-text search across all conversation logs.

```
$ pickel search "retry logic"

⛏️  3 results for retry logic

  my-app a1b2c3d4
    2026-05-10 14:32 🧑 Add retry logic to the API client
    2026-05-10 14:33 🤖 Added exponential backoff with max 3 retries...
```

Options:
- `-p, --project` — Filter by project name
- `-m, --max` — Max results (default: 10)
- `--json` — JSON output

### `pickel projects`

List all projects with session counts and sizes.

```
$ pickel projects

⛏️  12 projects

  PROJECT                     SESSIONS     SIZE   LAST
  ─────────────────────────── ──────── ──────── ──────
  my-app                            24  120.5M     1h
  api-server                        18   85.2M     3d
  docs-site                          7   12.0M     5d
  ...

  58 sessions · 240 MB total
```

### `pickel last <project>`

Show the last session summary for a project.

```
$ pickel last my-app

⛏️  my-app — last session (1h ago)

  session  a1b2c3d4-e5f6
  model    claude-sonnet-4-5
  turns    23
  tokens   45,200

  Last exchange:
    🧑 Can you add tests for the retry logic?
    🤖 Added 4 test cases covering timeout, network error...
```

### `pickel context <session-id>`

Extract context from a specific session. Useful for resuming work.

```
$ pickel context a1b2c3d4

⛏️  my-app a1b2c3d4-e5f6

  User messages (23 total):
      1. Add retry logic to the API client
      2. Make it configurable
      3. Add tests
      ...

  Tools used: Bash, Edit, Read, Write
```

## How It Works

Claude Code stores every conversation as JSONL files in `~/.claude/projects/`. Each line is a JSON object — user messages, assistant responses, tool calls, system events.

pickel reads these files line by line (streaming, no memory bloat) and searches through them. That's it. A thin wrapper over `json.loads()` and string matching.

```
~/.claude/projects/
├── my-app/
│   ├── a1b2c3d4.jsonl      ← conversation log
│   ├── e5f6g7h8.jsonl
│   └── memory/MEMORY.md
├── api-server/
│   └── ...
└── ...
```

## Design

- **Zero dependencies** — Python 3.8+, stdlib only
- **Single file** — one Python script
- **Streaming** — reads line by line, never loads full files into memory
- **Fast** — same principle as grep
- **NO_COLOR** — respects `NO_COLOR` and `FORCE_COLOR` env vars
- **Pipe-friendly** — `--json` flag on every command

## License

MIT
