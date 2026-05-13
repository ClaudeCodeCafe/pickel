# ⛏️ pickel

A pickaxe for mining Claude Code conversation logs.

One command to search all your Claude Code conversations.

## Install

```bash
# Homebrew
brew install ClaudeCodeCafe/tap/pickel

# pip
pip install pickel

# or just download
curl -fsSL https://raw.githubusercontent.com/ClaudeCodeCafe/pickel/master/pickel -o /usr/local/bin/pickel
chmod +x /usr/local/bin/pickel
```

## Usage

```bash
# Search across all conversations
pickel search "cscan"

# Filter by project
pickel search "VHS" -p garage

# List all projects
pickel projects

# Last session summary
pickel last garage

# Session context
pickel context c20437aa
```

## Commands

### `pickel search <query>`

Full-text search across all conversation logs.

```
$ pickel search "cscan"

⛏️  10 results for cscan

  garage c20437aa
    2026-05-13 17:02 🧑 cscan めっちゃいいじゃん！
    2026-05-13 17:02 🤖 cscan — Claude の設定をスキャンして可視化する...
```

Options:
- `-p, --project` — Filter by project name
- `-m, --max` — Max results (default: 10)
- `--json` — JSON output

### `pickel projects`

List all projects with session counts and sizes.

```
$ pickel projects

⛏️  42 projects

  PROJECT                     SESSIONS     SIZE   LAST
  ─────────────────────────── ──────── ──────── ──────
  garage                            15  326.9M     0m
  claude-code-cafe                  52  579.0M     2d
  antenna                           42   11.0M     8d
  ...

  2,809 sessions · 5.9 GB total
```

### `pickel last <project>`

Show the last session summary for a project.

```
$ pickel last garage

⛏️  garage — last session (2h ago)

  session  c20437aa-e14
  model    claude-opus-4-6
  turns    48
  tokens   125,000

  Last exchange:
    🧑 pickel search "cscan"
    🤖 Found 10 results...
```

### `pickel context <session-id>`

Extract context from a specific session. Useful for resuming work.

```
$ pickel context c20437aa

⛏️  garage c20437aa-e14

  User messages (48 total):
      1. CSS のクリーンアップしよう
      2. コンポーネントギャラリー欲しい
      3. アニメーション入れたい
      ...

  Tools used: Bash, Edit, Read, Write, Agent
```

## How It Works

Claude Code stores every conversation as JSONL files in `~/.claude/projects/`. Each line is a JSON object — user messages, assistant responses, tool calls, system events.

pickel reads these files line by line (streaming, no memory bloat) and searches through them. That's it. A thin wrapper over `json.loads()` and string matching.

```
~/.claude/projects/          pickel searches here
├── garage/                  ⛏️ 15 sessions, 326MB
│   ├── abc123.jsonl         ← conversation log
│   ├── def456.jsonl
│   └── memory/MEMORY.md
├── antenna/                 ⛏️ 42 sessions, 11MB
│   └── ...
└── ...                      42 projects, 5.9GB total
```

## Design

- **Zero dependencies** — Python 3.8+, stdlib only
- **Single file** — `pickel` is one 450-line Python script
- **Streaming** — reads line by line, never loads full files into memory
- **Fast** — searches 6GB in seconds (same principle as grep)
- **NO_COLOR** — respects `NO_COLOR` and `FORCE_COLOR` env vars
- **Pipe-friendly** — `--json` flag on every command

## Part of the CCC Toolchain

| Tool | Language | What it does |
|------|----------|-------------|
| [vshot](https://github.com/ClaudeCodeCafe/vshot) | bash | Video → montage for AI |
| [cping](https://github.com/ClaudeCodeCafe/cping) | Python | Ping Claude's service status |
| **pickel** | Python | Mine conversation logs |

## License

MIT
