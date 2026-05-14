# BRIEF: pickel mine — v0.5.0

## ゴール

`pickel mine` コマンドを追加し、PreCompact hook で自動的に会話の重要情報を抽出・コンテキストに注入する機能を実装する。
hooks/hooks.json を追加して、プラグインインストール時に自動で hook が登録されるようにする。

## 背景

Claude Code の PreCompact hook は stdin で `transcript_path`（会話ログのパス）を受け取り、stdout で `additionalContext`（最大10,000文字）を返すとコンパクト後のコンテキストに残る。
これを利用して「入れるだけで AI が忘れなくなる」機能を実装する。

## やること

### 1. `cmd_mine` 関数を cli.py に追加

PreCompact hook から呼ばれるメインコマンド。

**入力:** stdin から JSON を読む

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/path",
  "hook_event_name": "PreCompact",
  "compaction_trigger": "manual|auto"
}
```

**処理:**

1. stdin から JSON をパース（stdin が空 or パース失敗時は transcript_path なしで動作）
2. transcript_path があればそのファイルを `iter_messages()` で読む
3. 以下のカテゴリで重要情報を抽出:

**Decisions（決定事項）:**
- ユーザーメッセージから「〜に決めた」「〜でいこう」「〜で確定」「let's go with」「decided」等のパターン
- アシスタントの「確定しました」「〜に決まりました」等

**Discoveries（発見）:**
- 「わかった」「発見」「found」「turns out」「actually」等
- エラー解決: 「原因は」「fix」「solved」「直った」等

**Errors & Fixes（エラーと修正）:**
- ユーザーの修正指示: 既存の `correction_patterns` を再利用
- 「404」「error」「failed」「bug」等 + その後の解決

**Unfinished（未完了）:**
- 「次は」「TODO」「後で」「残課題」「next」「later」等
- 最後のユーザーメッセージも含める（中断された作業の可能性）

4. 抽出結果を additionalContext 形式で stdout に出力:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreCompact",
    "additionalContext": "# pickel mine — Session Context Rescue\n\n## Decisions\n- ...\n\n## Discoveries\n- ...\n\n## Unfinished\n- ..."
  }
}
```

**注意:**
- additionalContext は最大 10,000 文字。超えたら末尾を切り詰める
- 抽出結果が空の場合でも最低限 "No significant context extracted" を返す
- パターンマッチはシンプルに。正規表現で。LLM は使わない
- stdin が空（hook 以外から手動実行された場合）でも動作する: transcript_path がなければ「現在のプロジェクトの最新セッション」にフォールバック

### 2. `mine` サブコマンドを argparse に追加

```python
mi = sub.add_parser("mine", help="Extract key context from session (PreCompact hook)")
mi.add_argument("--post", action="store_true", help="PostCompact mode (logging only)")
mi.add_argument("--transcript", help="Path to transcript file (overrides stdin)")
mi.add_argument("-p", "--project", help="Project name (for fallback)")
mi.add_argument("--json", action="store_true", help="JSON output (raw extracted data)")
mi.add_argument("--dry-run", action="store_true", help="Show what would be extracted without hook output")
```

### 3. hooks/hooks.json を新規作成

```json
{
  "description": "pickel mine — Auto-rescue context on compact",
  "hooks": {
    "PreCompact": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/pickel mine"
          }
        ]
      }
    ]
  }
}
```

PostCompact は v0.5.0 では入れない（シンプルに保つ）。

### 4. バージョンを 0.5.0 に上げる

以下の全箇所:
- `pickel` スクリプト内の `__version__`
- `src/pickel/cli.py` の `__version__`
- `pyproject.toml` の `version`
- `.claude-plugin/plugin.json` の `version`
- `.claude-plugin/marketplace.json` の `version`

### 5. main() のコマンドディスパッチに mine を追加

```python
elif cmd == "mine":
    cmd_mine(args)
```

## やらないこと

- 永続化（~/.pickel/ores/ への保存） → v0.6.0
- LLM 要約 → 将来
- config.toml → 将来
- /pickel:setup の拡張 → 将来
- PostCompact hook → 将来
- commands/mine.md スラッシュコマンド → 将来

## テスト

### 手動テスト

```bash
# stdin なしで最新セッションから抽出
echo '{}' | pickel mine --dry-run

# transcript 指定で抽出
pickel mine --transcript ~/.claude/projects/.../session.jsonl --dry-run

# JSON 出力
echo '{"transcript_path": "/path/to/session.jsonl"}' | pickel mine --json

# hook 形式の出力確認（additionalContext が含まれる）
echo '{"transcript_path": "/path/to/session.jsonl", "hook_event_name": "PreCompact"}' | pickel mine
```

### smoke.sh に追加

```bash
# mine command
echo '{}' | "$PICKEL" mine --dry-run
```

## 注意

- 既存コードを壊さない
- `pickel` と `src/pickel/cli.py` は同期させる（同じ内容）
- git add -A は使わない
- コミットメッセージに Co-Authored-By は含めない
- コミットはしない（レビュー後にもりけんさんがコミットする）
