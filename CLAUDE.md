# CLAUDE.md — pickel

A zero-dependency Python CLI for mining Claude Code conversation logs.

## Setup
```bash
pip install ruff   # required for lint / format
```

## Rules
- `pickel` and `src/pickel/cli.py` must always stay in sync (pickel = shebang + cli.py)
- No external dependencies. Python standard library only
- Maintain Python 3.8 compatibility (`from __future__ import annotations` required)
- Run `ruff check pickel src/` and `ruff format --check pickel src/` after changes
- Version must be synced across all 6 locations:
  - `src/pickel/cli.py` (`__version__`)
  - `src/pickel/__init__.py` (`__version__`)
  - `pyproject.toml` (`version`)
  - `pickel` (standalone script, synced from cli.py)
  - `.claude-plugin/plugin.json` (`version`)
  - `.claude-plugin/marketplace.json` (`metadata.version` + `plugins[0].version`)
- Do NOT include `Co-Authored-By: Claude` in commit messages
