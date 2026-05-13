# pickel

A pickaxe for mining Claude Code conversation logs.

A zero-dependency Python CLI that searches through your
`~/.claude/projects/` conversation history and returns results instantly.

## Install

### pip / pipx

```bash
pipx install pickel-cli    # recommended (isolated env)
pip install pickel-cli      # or with pip
```

### Homebrew

```bash
brew install ClaudeCodeCafe/tap/pickel
```

### Manual

```bash
curl -fsSL https://raw.githubusercontent.com/ClaudeCodeCafe/pickel/master/pickel -o /usr/local/bin/pickel
chmod +x /usr/local/bin/pickel
```

## Usage

```bash
pickel search "retry logic"
```

```
⛏️  3 results for retry logic

  my-app
    a1b2c3d4
      2026-05-10 14:32 🧑 Add retry logic to the API client
      2026-05-10 14:33 🤖 Added exponential backoff with max 3 retries...
      2026-05-10 14:35 🧑 Make the max retries configurable
```

### Commands

| Command | Description |
| ------- | ----------- |
| `search <query>` | Full-text search across all conversations |
| `projects` | List all projects with session counts and sizes |
| `last <project>` | Show the last session summary for a project |
| `context <session>` | Show session context (user messages + tools) |
| `chat` | Show session conversation in chat format |
| `errors` | Extract user corrections and API errors |
| `tools` | Show tool usage frequency |
| `cost` | Estimate token costs by model |

### Search Options

| Flag | Description |
| ---- | ----------- |
| `-p, --project` | Filter by project name |
| `-m, --max` | Max results (default: 10) |
| `-r, --regex` | Use regex search |
| `--since YYYY-MM-DD` | Filter sessions since date |
| `--today` | Only today's sessions |
| `--compact` | Compact output (for AI tools) |
| `--json` | Output as JSON |

### Global Options

| Flag | Description |
| ---- | ----------- |
| `-q, --quiet` | Suppress warnings on stderr |
| `--json` | JSON output (available on all commands) |

### Examples

```bash
# Search all projects
pickel search "auth middleware"

# Search within a specific project
pickel search "migration" -p my-app

# Regex search
pickel search -r "TODO|FIXME|HACK"

# Today's sessions only
pickel search "deploy" --today

# List projects
pickel projects

# What did I last work on?
pickel last my-app

# Show session context
pickel context a1b2c3d4

# View a chat session
pickel chat -p my-app

# Estimate costs
pickel cost --month
```

### Project List

```
$ pickel projects

⛏️  12 projects

  PROJECT                     SESSIONS     SIZE   LAST
  ─────────────────────────── ──────── ──────── ──────
  my-app                            24  120.5M     1h
  api-server                        18   85.2M     3d
  docs-site                          7   12.0M     5d
  ...

  58 sessions · 0.2 GB total
```

### Last Session

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

## How It Works

Claude Code stores conversations as JSONL files in `~/.claude/projects/`.
pickel streams through these files line by line and matches your query.
Same principle as grep — fast, no memory bloat.

## Requirements

- Python 3.8+

No external packages required. Uses only the Python standard library.

## License

MIT
