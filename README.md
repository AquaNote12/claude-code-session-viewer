# claude-code-session-viewer

Claude Code のセッション履歴を、メッセージアプリ風の吹き出し表示で 1 ファイルの HTML に書き出す Claude Code 用 skill。

## できること

- 指定したセッションのやり取りを、時系列順に上から吹き出しで表示する
- Claude の吹き出しには、モデル（例: `claude-opus-5-5`）と effort（例: `high`）を表示する
- トークン数を、Claude の吹き出しごとと、セッション全体の合計（モデル別の内訳つき）で表示する。出力と入力を分け、入力のうちキャッシュ読み込みの分も示す。サブエージェントの分は合計に含め、内訳を別に示す。料金は表示しない
- 長いメッセージは折り畳む。折り畳んでいるときは概要（Claude は最後のテキストの冒頭と、使ったツールの集計）を表示する
- メッセージ単位の目次をサイドバーに表示する。目次の ON/OFF を切り替えられる
- ワンクリックで HTML をダウンロード、またはクリップボードにコピーできる
- ツール呼び出し、思考、システム行（コマンド実行・圧縮・モード切り替えなど）の表示を切り替えられる
- サブエージェントのやり取りを、呼び出した Agent ツールの中に入れ子で表示する
- ダークモードとスマホ幅に対応している

外部ライブラリや CDN は使っていない。生成した HTML はオフラインでも開ける。

## 必要なもの

- Claude Code（CLI・VS Code 拡張機能のどちらでも使える）
- Python 3.9 以上（macOS 標準の `python3` で動く。追加のパッケージは不要）

この skill は Claude Code 専用。Claude Code が保存するセッション履歴（`~/.claude/projects/`）を読み、Claude Code 独自の置換（`${CLAUDE_SKILL_DIR}` など）も使うため、Cursor や Codex など他のエージェントに入れても動かない。

## インストール

次のどちらかの方法で、**ユーザー単位**（`~/.claude/skills/`）に入れる。ユーザー単位で入れれば、どのプロジェクトでも、CLI と VS Code 拡張機能の両方で使える。

### 方法 1: GitHub CLI（推奨）

GitHub CLI v2.90.0 以上が必要（`gh skill` は 2026 年 4 月に追加されたプレビュー機能）。古い場合は先に gh を更新する。

```bash
gh skill install AquaNote12/claude-code-session-viewer claude-code-session-viewer --agent claude-code --scope user
```

`--agent claude-code --scope user` は省略しないこと。省略すると、GitHub Copilot 向けに、今いる git リポジトリの中へ入ってしまう。

特定のバージョンに固定する場合は、skill 名の後ろに `@<タグ>` を付ける（例: `claude-code-session-viewer@v0.1.0`）。

更新:

```bash
gh skill update
```

### 方法 2: skills CLI（Node.js が必要）

```bash
npx skills add AquaNote12/claude-code-session-viewer --skill claude-code-session-viewer -a claude-code -g
```

`-g` を付けないと、今いるプロジェクトの中にだけ入る。

更新・削除:

```bash
npx skills update claude-code-session-viewer
npx skills remove claude-code-session-viewer
```

### 方法 3: 手動で配置

上の 2 つが使えない環境向け。リポジトリを clone し、skill のディレクトリを `~/.claude/skills/` にシンボリックリンクする。

```bash
git clone https://github.com/AquaNote12/claude-code-session-viewer.git
ln -s "$(pwd)/claude-code-session-viewer/skills/claude-code-session-viewer" ~/.claude/skills/claude-code-session-viewer
```

更新は clone したディレクトリで `git pull` する。

### インストール後

すでに開いている Claude Code のセッションに skill が出てこない場合は、新しいセッションを開く。

## 使い方

Claude Code の中で次のように呼び出す。

```
/claude-code-session-viewer              # 現在のセッションを書き出す
/claude-code-session-viewer list         # セッション一覧から選ぶ
/claude-code-session-viewer 1a2b3c4d     # ID（先頭一致）で指定する
```

「このセッションを HTML にして」のように頼んでも起動する。

スクリプトを直接実行することもできる（パスはリポジトリのルートから）。

```bash
python3 skills/claude-code-session-viewer/scripts/render_session.py list [--all] [--limit N] [--project DIR]
python3 skills/claude-code-session-viewer/scripts/render_session.py render <セッションID | JSONLのパス> [--out PATH] [--no-subagents]
```

## リポジトリの構成

```
claude-code-session-viewer/
├── skills/
│   └── claude-code-session-viewer/      # skill 本体（この単位でインストールされる）
│       ├── SKILL.md
│       └── scripts/render_session.py
├── LICENSE
├── README.md
└── .gitignore
```

`skills/<skill名>/SKILL.md` の配置は Agent Skills 仕様の規約に合わせている。`gh skill install` と `npx skills add` はこの配置から skill を見つける。

出力先の既定は `~/Downloads/claude-code-sessions/` 。

## 表示するもの・しないもの

人が読んで意味のあるものはなるべく表示し、内部向けの記録は表示しない。

| 表示する | 表示しない |
|---|---|
| ユーザーの発言（Claude の作業中に送った発言も含む）、添付画像 | API リクエストの記録、トークン残量の注記 |
| Claude のテキスト、思考（中身が記録されている場合のみ） | ツール一覧・Skill 一覧などの差分通知 |
| ツール呼び出しと結果（Bash のコマンド、Edit の差分、ToDo など） | 環境情報・日付・言語設定などの自動付与情報 |
| サブエージェントのやり取り | ファイル履歴のスナップショット |
| Skill の読み込み、フックのエラー | ローカルコマンドの注意書き、画像パスの注記 |
| スラッシュコマンドとその出力、バックグラウンドタスクの通知 | 中身が空の思考ブロック（暗号化された思考） |
| 会話の圧縮と要約、プランモード・オートモードの切り替え、PR との紐付け | |
| IDE で開いていたファイル・選択範囲 | |

## 注意点

- セッション履歴の JSONL は Claude Code の内部形式で、公式には文書化されていない。Claude Code のバージョンアップで形式が変わると、表示が崩れる可能性がある。知らない種類のレコードは読み飛ばすようにしてある。
- 既定では古いセッションファイルは一定期間（`cleanupPeriodDays`）で自動削除される。
- ツール結果は 1 件あたり 30,000 文字で切り詰める。画像は HTML に埋め込むので、画像の多いセッションはファイルが大きくなる。
- HTML にはツールの実行結果やファイルの中身もそのまま入る。共有する前に機密情報が含まれていないか確認すること。
- `file://` で開いたページではブラウザによってクリップボード API が使えない。その場合は `document.execCommand("copy")` で代わりにコピーする。

## ライセンス

[MIT License](LICENSE)
