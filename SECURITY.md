# Security policy

English | [日本語](#日本語)

## Supported versions

Only the latest release is supported. Fixes are published as a new release.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately from the repository's **Security** tab → **Report a vulnerability** (GitHub private vulnerability reporting). Include:

- what an attacker can do, and what they need first (for example, a crafted transcript, or a file they can write)
- steps to reproduce, ideally with a made-up transcript; please do not send real session history
- the version (release tag or commit) and your OS and Python version

This is a personal project maintained on a best-effort basis. You will get a reply when the report has been read, and a confirmed problem will be fixed in a new release as soon as practical.

## Scope

Things that are in scope include:

- the script running something other than intended, or writing anywhere other than the output file and its directory (`render`, `list`, `open`)
- a generated page running script other than its own `app.js`, loading anything from the network, or navigating away by itself
- a transcript making Claude do something the skill's instructions do not ask for, through the script's output
- `open` opening a page that can run script other than the tool's own `app.js`, or navigate away by itself (`open` does not detect added text or plain links; that is a known limit)

Out of scope: what you choose to put in a page and share. The page contains the session as it is; see "Privacy and sharing" in the README.

---

## 日本語

### 対象のバージョン

最新のリリースだけです。修正は新しいリリースとして公開します。

### 報告の方法

セキュリティの問題は **公開の Issue に書かないでください**。リポジトリの **Security** タブ → **Report a vulnerability**（GitHub の非公開の脆弱性報告）から報告してください。次の内容を書いてください。

- 攻撃者に何ができるか、そのために何が必要か（例: 細工した履歴、書き込めるファイル）
- 再現手順。できれば架空の履歴で。実際のセッション履歴は送らないでください
- バージョン（リリースのタグかコミット）と、OS と Python のバージョン

個人で保守しているため、対応は可能な範囲になります。報告を読んだら返信し、確認できた問題はできるだけ早く新しいリリースで修正します。

### 対象範囲

対象になるものの例です。

- スクリプトが意図しないものを実行する、または出力ファイルとそのディレクトリ以外に書き込む（`render`、`list`、`open`）
- 生成したページが、自身の `app.js` 以外のスクリプトを実行する、ネットワークから何かを読み込む、または勝手に別のページへ移動する
- 履歴の内容が、スクリプトの出力を通じて、skill の指示にない動作を Claude にさせる
- `open` が、`app.js` 以外のスクリプトを実行できるページや、勝手に別のページへ移動するページを開く（文や普通のリンクを書き足したページは検出しません。これは既知の制限です）

対象外: ページに何を入れて共有するか。ページにはセッションの内容がそのまま入ります。README の「プライバシーと共有」を参照してください。
