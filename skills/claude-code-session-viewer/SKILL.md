---
name: claude-code-session-viewer
description: Claude Code のセッション履歴を、メッセージアプリ風の吹き出し表示で 1 ファイルの HTML に書き出す。目次サイドバー、長文の折り畳み、モデルと effort の表示、ワンクリックでのダウンロードとコピーに対応する。「このセッションを HTML にして」「セッション履歴を出力して」「会話ログを共有用に書き出して」のように、Claude Code のセッションや会話履歴（transcript）を HTML で見たい・残したい・共有したいと言われたときに使う。
argument-hint: "[セッションID | current | list]"
allowed-tools: Bash(python3 *)
---

# Claude Code セッションを HTML に書き出す

`~/.claude/projects/` に保存されているセッション履歴（JSONL）を、同梱スクリプトで HTML に変換する。
変換はスクリプトがすべて行う。JSONL や生成した HTML を Read で読み込んだり、HTML を手で書いたりしない（長いセッションでは大量のトークンを使い、結果も安定しないため）。

スクリプト: `${CLAUDE_SKILL_DIR}/scripts/render_session.py`
（`${CLAUDE_SKILL_DIR}` が置き換わっていない場合は、この SKILL.md と同じディレクトリにある `scripts/render_session.py` を使う。インストール方法によって場所が変わるため、パスを決め打ちしない）

## 手順

1. 対象のセッションを決める。引数は `$ARGUMENTS`。
   - 空、`current`、「このセッション」など → 現在のセッション `${CLAUDE_SESSION_ID}`
   - `list`、または対象がはっきりしない → 次を実行し、一覧からどれにするかユーザーに聞く
     ```bash
     python3 "${CLAUDE_SKILL_DIR}/scripts/render_session.py" list
     ```
     別のプロジェクトのセッションも探すときは `--all` を付ける。
   - セッション ID（先頭 8 文字程度でも可）や JSONL ファイルのパス → そのまま使う
2. 変換する。
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/render_session.py" render <セッション> [--out <ファイルまたはディレクトリ>]
   ```
   - 出力先の既定は `~/Downloads/claude-code-sessions/<タイトル>_<ID先頭8文字>.html`。ユーザーが場所を指定したときだけ `--out` を付ける。
   - サブエージェントのやり取りは既定で含める。不要と言われたら `--no-subagents` を付ける。
3. スクリプトが表示した出力パスをそのままユーザーに伝える。ブラウザで開くか聞き、希望があれば `open <出力パス>` を実行する。

## 補足

- 現在のセッションを変換した場合、変換を実行した時点までのやり取りが入る。
- HTML にはツールの実行結果やファイルの中身もそのまま入る。共有する前に、機密情報が含まれていないか確認するようユーザーに一言添える。
- ID が複数のセッションに一致した、またはセッションが見つからないとスクリプトが言った場合は、その内容をユーザーに伝えて ID を確認する。
