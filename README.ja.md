[English](README.md) | [日本語](README.ja.md)

# pickel

Claude Code の会話ログを採掘するつるはし。

外部依存ゼロの Python CLI。`~/.claude/projects/` の会話履歴を即座に検索できます。

## インストール

### Option A: Claude Code プラグイン（推奨）

```bash
/plugin marketplace add ClaudeCodeCafe/pickel
/plugin install pickel@pickel
```

そのまま使えます:

```
/pickel:search "auth middleware"
/pickel:last my-app
/pickel:cost --today
/pickel:setup
```

### Option B: CLI

#### pip / pipx

```bash
pipx install pickel-cli    # 推奨（隔離環境）
pip install pickel-cli      # pip でも可
```

#### Homebrew

```bash
brew install ClaudeCodeCafe/tap/pickel
```

#### 手動インストール

```bash
curl -fsSL https://raw.githubusercontent.com/ClaudeCodeCafe/pickel/master/pickel -o /usr/local/bin/pickel
chmod +x /usr/local/bin/pickel
```

## 使い方

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

### コマンド一覧

| コマンド | 説明 |
| ------- | ----------- |
| `search <query>` | 全会話ログの全文検索 |
| `projects` | プロジェクト一覧（セッション数・サイズ付き） |
| `last <project>` | プロジェクトの最新セッションを表示 |
| `context <session>` | セッションのコンテキスト（ユーザーメッセージ + ツール） |
| `chat [-p PROJECT \| SESSION]` | セッションの会話をチャット形式で表示 |
| `errors` | ユーザーの修正指示と API エラーを抽出 |
| `tools` | ツール使用頻度を表示 |
| `cost` | モデル別トークンコスト推定 |
| `mine` | コンパクト時にコンテキストを自動採掘（PreCompact hook） |

### 検索オプション

| フラグ | 説明 |
| ---- | ----------- |
| `-p, --project` | プロジェクト名でフィルタ |
| `-m, --max` | 最大結果数（デフォルト: 10） |
| `-r, --regex` | 正規表現で検索 |
| `--since YYYY-MM-DD` | 指定日以降のセッションのみ（ファイル更新日時ベース） |
| `--today` | 今日のセッションのみ |
| `--compact` | コンパクト出力（AI ツール向け） |
| `--json` | JSON 出力 |

### グローバルオプション

| フラグ | 説明 |
| ---- | ----------- |
| `-q, --quiet` | stderr の警告を抑制 |

### コマンド共通オプション

`--json` は全サブコマンド（`search`, `projects`, `last`, `context`, `chat`, `errors`, `tools`, `cost`, `mine`）で利用可能。

### 使用例

```bash
# 全プロジェクトを検索
pickel search "auth middleware"

# 特定プロジェクト内を検索
pickel search "migration" -p my-app

# 正規表現で検索
pickel search -r "TODO|FIXME|HACK"

# 今日のセッションのみ
pickel search "deploy" --today

# プロジェクト一覧
pickel projects

# 最後に何をやった？
pickel last my-app

# セッションのコンテキスト表示
pickel context a1b2c3d4

# チャット形式で表示
pickel chat -p my-app

# コスト見積もり
pickel cost --month
```

### プロジェクト一覧

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

### 最新セッション

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

## Claude Code プラグイン

pickel は Claude Code マーケットプレイスプラグインとして利用できます。

### インストール

```bash
# Claude Code マーケットプレイスからインストール
/plugin marketplace add ClaudeCodeCafe/pickel
/plugin install pickel@pickel
```

### プラグインコマンド

| コマンド | 説明 |
| ------- | ----------- |
| `/pickel:search <query>` | 過去の会話ログを検索 |
| `/pickel:last [project]` | プロジェクトの最新セッションを表示 |
| `/pickel:cost` | トークンコスト推定 |
| `/pickel:setup` | プラグインの準備状態を確認 |

### Hook: コンテキスト自動採掘

pickel は Claude Code が会話をコンパクトする際、重要なコンテキストを自動で保持します。設定不要 — プラグインをインストールするだけ。

コンパクト時に `PreCompact` hook が以下を抽出します:

- **Decisions** — セッション中に決定したこと
- **Discoveries** — 学んだこと、発見したこと
- **Errors & Fixes** — 遭遇した問題とその解決方法
- **Unfinished** — 進行中だったタスク

抽出されたコンテキストはコンパクト後の会話に注入されるため、Claude が文脈を見失いません。

手動で実行することもできます:

```bash
pickel mine --dry-run                          # 抽出内容をプレビュー
pickel mine --transcript path/to/session.jsonl  # 特定のセッションから抽出
```

### スキル: 会話マイニング

プラグインには `conversation-mining` スキルが含まれており、過去の作業について質問すると自動でトリガーされます:

- 「前のセッションで何やった？」
- 「この問題前に解決した？」
- 「先週何を作った？」
- "Did we implement this before?"

Claude が自動的に `pickel search` や `pickel last` を実行して、関連する過去のセッションを表示します。

## セキュリティ / プライバシー

Claude Code の会話ログには、API キー、パスワード、内部 URL、チャットに貼り付けたコードなどの機密情報が含まれている場合があります。以下にご注意ください:

- **`--json` 出力には生のメッセージテキストが含まれます。** 公開ログや共有ダッシュボードにパイプする際はリダクションを行ってください。
- **`~/.claude/projects/` は暗号化されていません。** ホームディレクトリへの読み取りアクセスがあれば誰でも会話履歴を読めます。
- **`search` と `chat` はそのままの内容を表示します。** ターミナル出力やスクリーンショットの共有には注意してください。

pickel はネットワーク経由でデータを送信しません。全ての処理はローカルで完結します。

## 仕組み

Claude Code は会話を `~/.claude/projects/` に JSONL ファイルとして保存しています。
pickel はこれらのファイルを1行ずつストリーム処理してクエリにマッチさせます。
grep と同じ原理 — 高速で、メモリを圧迫しません。

## 動作要件

- Python 3.8+

外部パッケージ不要。Python 標準ライブラリのみで動作します。

## コントリビュート

```bash
git clone https://github.com/ClaudeCodeCafe/pickel.git
cd pickel
pip install ruff
bash tests/smoke.sh          # テスト実行
ruff check pickel src/        # lint
ruff format --check pickel src/  # フォーマットチェック
```

PR 歓迎です。`smoke.sh` が通ること、`ruff` がエラーなしであることを確認してください。

## ライセンス

MIT
