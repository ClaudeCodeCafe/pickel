# CLAUDE.md — pickel

Claude Code 会話ログを検索する Python CLI。依存ゼロ。

## ルール
- `pickel` と `src/pickel/cli.py` は常に同期（pickel = shebang + cli.py）
- 依存追加禁止。Python 標準ライブラリのみ
- 変更後は `ruff check pickel src/` と `ruff format --check pickel src/` を実行
- git commit に Co-Authored-By: Claude <noreply@anthropic.com> を含める
