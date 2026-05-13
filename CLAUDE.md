# CLAUDE.md — pickel

Claude Code 会話ログを検索する Python CLI。依存ゼロ。

## セットアップ
```bash
pip install ruff   # lint / format に必要
```

## ルール
- `pickel` と `src/pickel/cli.py` は常に同期（pickel = shebang + cli.py）
- 依存追加禁止。Python 標準ライブラリのみ
- Python 3.8 互換を維持（`from __future__ import annotations` 必須）
- 変更後は `ruff check pickel src/` と `ruff format --check pickel src/` を実行
- バージョンは `src/pickel/cli.py`, `src/pickel/__init__.py`, `pyproject.toml`, `pickel` の 4 箇所を同期
- git commit に Co-Authored-By: Claude <noreply@anthropic.com> を含める
