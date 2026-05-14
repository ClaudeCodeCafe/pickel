# pickel

A pickaxe for mining Claude Code conversation logs.

A zero-dependency Python CLI that searches through your
`~/.claude/projects/` conversation history and returns results instantly.

## Install

### Option A: Claude Code Plugin (Recommended)

```bash
/plugin marketplace add ClaudeCodeCafe/pickel
/plugin install pickel@pickel
```

Then use directly:

```
/pickel:search "auth middleware"
/pickel:last my-app
/pickel:cost --today
/pickel:setup
```

### Option B: CLI

#### pip / pipx

```bash
pipx install pickel-cli    # recommended (isolated env)
pip install pickel-cli      # or with pip
```

#### Homebrew

```bash
brew install ClaudeCodeCafe/tap/pickel
```

#### Manual

```bash
curl -fsSL https://raw.githubusercontent.com/ClaudeCodeCafe/pickel/master/pickel -o /usr/local/bin/pickel
chmod +x /usr/local/bin/pickel
```

## Usage

```bash
pickel search "retry logic"
```

```
3 results for retry logic

  my-app
    a1b2c3d4
      2026-05-10 14:32 U Add retry logic to the API client
      2026-05-10 14:33 A Added exponential backoff with max 3 retries...
      2026-05-10 14:35 U Make the max retries configurable
```

### Commands

| Command | Description |
| ------- | ----------- |
| `search <query>` | Full-text search across all conversations |
| `projects` | List all projects with session counts and sizes |
| `last <project>` | Show the last session summary for a project |
| `context <session>` | Show session context (user messages + tools) |
| `chat [-p PROJECT \| SESSION]` | Show session conversation in chat format |
| `errors` | Extract user corrections and API errors |
| `tools` | Show tool usage frequency |
| `cost` | Estimate token costs by model |
| `mine` | Auto-rescue context on compact (PreCompact hook) |

### Search Options

| Flag | Description |
| ---- | ----------- |
| `-p, --project` | Filter by project name |
| `-m, --max` | Max results (default: 10) |
| `-r, --regex` | Use regex search |
| `--since YYYY-MM-DD` | Filter sessions since date (by file modification time) |
| `--today` | Only today's sessions (by file modification time) |
| `--compact` | Compact output (for AI tools) |
| `--json` | JSON output |

### Global Options

| Flag | Description |
| ---- | ----------- |
| `-q, --quiet` | Suppress warnings on stderr |

### Per-Command Options

`--json` is available on all subcommands (`search`, `projects`, `last`, `context`, `chat`, `errors`, `tools`, `cost`, `mine`).

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

  12 projects

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

  my-app — last session (1h ago)

  session  a1b2c3d4-e5f6
  model    claude-sonnet-4-5
  turns    23
  tokens   45,200

  Last exchange:
    U Can you add tests for the retry logic?
    A Added 4 test cases covering timeout, network error...
```

## Claude Code Plugin

pickel is available as a Claude Code marketplace plugin.

### Install

Install via the Claude Code marketplace, or add it directly to your project:

```bash
# In your Claude Code settings or CLAUDE.md
# Plugin source: https://github.com/ClaudeCodeCafe/pickel
```

### Commands

| Command | Description |
| ------- | ----------- |
| `/pickel:search <query>` | Search past conversation logs |
| `/pickel:last [project]` | Show the last session for a project |
| `/pickel:cost` | Estimate token costs |
| `/pickel:setup` | Check plugin readiness |

### Hook: Auto Context Rescue

pickel automatically preserves important context when Claude Code compacts your conversation. No configuration needed — just install the plugin.

When a conversation is compacted, the `PreCompact` hook extracts:

- **Decisions** — what was decided during the session
- **Discoveries** — what was learned or found
- **Errors & Fixes** — problems encountered and how they were solved
- **Unfinished** — tasks that were in progress

The extracted context is injected back into the compacted conversation, so Claude doesn't lose track of what happened.

You can also run it manually:

```bash
pickel mine --dry-run                          # preview what would be extracted
pickel mine --transcript path/to/session.jsonl  # extract from a specific session
```

### Skill: Conversation Mining

The plugin includes a `conversation-mining` skill that auto-triggers when you ask about past work:

- "What did we do in the last session?"
- "Did we solve this problem before?"
- "What did I build last week?"
- "Did we implement this before?"

Claude will automatically run `pickel search` or `pickel last` to surface relevant past sessions.

## Security / Privacy

Claude Code conversation logs may contain sensitive information such as API
keys, passwords, internal URLs, or proprietary code snippets that were pasted
into the chat. Keep the following in mind:

- **`--json` output includes raw message text.** Avoid piping it to public
  logs or shared dashboards without redaction.
- **`~/.claude/projects/` is not encrypted.** Anyone with read access to your
  home directory can read your conversation history.
- **`search` and `chat` surface verbatim content.** Be cautious when sharing
  terminal output or screenshots.

pickel itself never sends data over the network. All processing is local.

## How It Works

Claude Code stores conversations as JSONL files in `~/.claude/projects/`.
pickel streams through these files line by line and matches your query.
Same principle as grep — fast, no memory bloat.

## Requirements

- Python 3.8+

No external packages required. Uses only the Python standard library.

## Contributing

```bash
git clone https://github.com/ClaudeCodeCafe/pickel.git
cd pickel
pip install ruff
bash tests/smoke.sh          # run tests
ruff check pickel src/        # lint
ruff format --check pickel src/  # format check
```

PRs welcome. Please ensure `smoke.sh` passes and `ruff` reports no errors.

## License

MIT
