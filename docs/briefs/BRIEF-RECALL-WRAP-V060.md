# BRIEF: pickel recall + wrap + ores — v0.6.0

## ゴール

`pickel recall`、`pickel wrap`、`pickel ores` を追加し、mine → wrap → recall の記憶サイクルを完成させる。
プロジェクトごとに会話の記憶が蓄積され、セッション開始時に前回の文脈を自動復帰する。

## 背景

v0.5.0 で `pickel mine`（PreCompact hook）を実装した。
mine はコンパクト時に重要情報を採掘して stdout に返すが、永続化はしない。
v0.6.0 では永続化レイヤー（~/.pickel/ores/）を追加し、セッション間で記憶を引き継ぐ。

## サイクル

```
SessionStart → recall（前回の文脈を思い出す）
  ↓ 作業
PreCompact → mine（文脈を採掘）→ 既に実装済み
  ↓ 作業続行
SessionEnd → wrap（セッションを記録・永続保存）
  ↓ 次回
SessionStart → recall（wrap の蓄積から思い出す）
```

## やること

### 1. `pickel wrap` — SessionEnd hook

セッション終了時にセッション全体の要約を採掘し、~/.pickel/ores/ に永続保存する。

**入力:** stdin から JSON を読む（SessionEnd の stdin）

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/path/to/project",
  "hook_event_name": "SessionEnd"
}
```

**処理:**

1. stdin から transcript_path と session_id を取得
2. cwd からプロジェクト名を推定（normalize_project_name 等で）
3. 既存の `_mine_extract_context()` を再利用して重要情報を抽出
4. コスト情報も追加で抽出（既存の cost 計算ロジックを再利用）
5. ~/.pickel/ores/{project_name}/ ディレクトリに保存

**保存先:** `~/.pickel/ores/{project_name}/{YYYY-MM-DD}-{session_id[:8]}.md`

**保存フォーマット:**
```markdown
# Ore — 2026-05-15 00:45
<!-- session: abc12345 | project: pickel | trigger: session-end -->

## Decisions
- pickel mine を v0.5.0 でリリース

## Discoveries
- PreCompact hook の additionalContext で 10,000 文字注入可能

## Errors & Fixes
- パストラバーサル脆弱性 → relative_to() で修正

## Unfinished
- recall + wrap の実装

## Cost
- Estimated: $2.34 (Sonnet 85%, Opus 15%)
```

**注意:**
- transcript_path がない場合は何もしない（exit 0）
- ディレクトリが存在しなければ作成（makedirs）
- 抽出結果が完全に空の場合は保存しない（空ファイルを作らない）
- async: true で呼ばれるので stdout は不要
- コスト計算は `cmd_cost` のロジックを関数として切り出して再利用

### 2. `pickel recall` — SessionStart hook

セッション開始時に、そのプロジェクトの最新 ore を読んで stdout に出力する。

**入力:** stdin から JSON（SessionStart の stdin）

```json
{
  "session_id": "def456",
  "cwd": "/path/to/project",
  "hook_event_name": "SessionStart",
  "source": "startup"
}
```

**処理:**

1. stdin から cwd を取得
2. cwd からプロジェクト名を推定
3. ~/.pickel/ores/{project_name}/ から最新の ore ファイルを読む
4. 内容を stdout に出力（system-reminder として表示される）

**stdout 形式:**
```json
{
  "continue": true,
  "suppressOutput": false,
  "status": "Previous session context loaded"
}
```

ただし SessionStart は additionalContext が使えない可能性がある。
その場合は単に stdout にテキストを出力して system-reminder に頼る。

確認事項: SessionStart の stdout で `hookSpecificOutput.additionalContext` が使えるか不明。
使えない場合のフォールバック:
- stdout にプレーンテキストで ore の内容を出力
- Claude Code が system-reminder として表示する

**注意:**
- source が `startup` の時のみ動作。`resume`/`compact`/`clear` では何もしない
- ore が存在しない場合は何も出力しない（exit 0）
- ore の内容が長い場合は 5,000 文字に切り詰める（セッション開始時の負荷を抑える）
- プロジェクト名が推定できない場合は何もしない

### 3. `pickel ores` — CLI コマンド

保存された ores の一覧と検索。

**サブコマンド:**
```bash
pickel ores                    # 全プロジェクトの ores 一覧
pickel ores -p my-app          # プロジェクト指定
pickel ores show               # 最新の ore を表示
pickel ores show -p my-app     # プロジェクト指定で最新表示
```

**一覧表示:**
```
  ~/.pickel/ores/

  PROJECT              ORES   LATEST      SIZE
  ──────────────────── ────── ────────── ──────
  pickel                    3  2h ago     4.2K
  my-app                    8  1d ago    12.0K
  api-server                2  3d ago     2.1K

  13 ores · 18.3K total
```

**show 表示:** ore ファイルの内容をそのまま出力。

**argparse:**
```python
ores_parser = sub.add_parser("ores", help="List and view saved ores")
ores_parser.add_argument("action", nargs="?", default="list", choices=["list", "show"])
ores_parser.add_argument("-p", "--project", help="Filter by project")
ores_parser.add_argument("--json", action="store_true", help="JSON output")
```

### 4. hooks/hooks.json に SessionStart と SessionEnd を追加

```json
{
  "description": "pickel — Auto-rescue context on compact, recall on start, wrap on end",
  "hooks": {
    "PreCompact": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "\"${CLAUDE_PLUGIN_ROOT}/pickel\" mine"
      }]
    }],
    "SessionStart": [{
      "matcher": "startup",
      "hooks": [{
        "type": "command",
        "command": "\"${CLAUDE_PLUGIN_ROOT}/pickel\" recall",
        "timeout": 10
      }]
    }],
    "SessionEnd": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "\"${CLAUDE_PLUGIN_ROOT}/pickel\" wrap",
        "async": true,
        "timeout": 30
      }]
    }]
  }
}
```

- recall: timeout 10秒（セッション開始をブロックしすぎない）
- wrap: async: true（セッション終了を待たせない）

### 5. コスト計算の関数切り出し

`cmd_cost` 内のトークン集計・コスト計算ロジックを `_calculate_session_cost(transcript_path)` として関数化。
wrap から再利用する。

### 6. mine にも永続化を追加（オプション）

`pickel mine` 実行時にも ore を保存するようにする。
ただし mine は PreCompact hook で呼ばれるので、stdout（additionalContext）が主。
保存は副作用として行う（失敗してもエラーにしない）。

mine の保存先: `~/.pickel/ores/{project_name}/{YYYY-MM-DD}-{session_id[:8]}-compact.md`
（wrap と区別するため `-compact` サフィックス）

### 7. バージョンを 0.6.0 に上げる

全5箇所:
- pickel スクリプトの __version__
- src/pickel/cli.py の __version__
- pyproject.toml の version
- .claude-plugin/plugin.json の version
- .claude-plugin/marketplace.json の version（2箇所）

### 8. smoke テスト追加

```bash
# wrap
[44] wrap with empty stdin
echo '{}' | "$PICKEL" wrap
check_exit_code 0 "[44] wrap with empty stdin exits 0"

# recall
[45] recall with empty stdin
echo '{}' | "$PICKEL" recall
check_exit_code 0 "[45] recall with empty stdin exits 0"

# ores list
[46] ores list
"$PICKEL" ores
check_exit_code 0 "[46] ores list exits 0"

# ores show (no ores yet may exit 0 with message)
[47] ores show
"$PICKEL" ores show
check_exit_code 0 "[47] ores show exits 0"

# ores --json
[48] ores --json
"$PICKEL" ores --json
check_exit_code 0 "[48] ores --json exits 0"
```

## やらないこと

- config.toml（設定ファイルは将来）
- claude-mem adapter / obsidian adapter
- LLM 要約
- /pickel:setup の拡張
- PostToolUse エラーアシスト（v0.7.0）

## 注意

- 既存の mine を壊さない
- pickel と src/pickel/cli.py は同期させる
- git add -A は使わない
- Co-Authored-By は含めない
- コミットしない（レビュー後）
