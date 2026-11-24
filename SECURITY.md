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

This is a personal project maintained on a best-effort basis. You will get a reply when the report has been read, and a fix will be released as soon as practical.

## Scope

Things that are in scope include:

- the script running something other than intended, or writing outside the output file (`render`, `list`, `open`)
- a generated page running script other than its own `app.js`, loading anything from the network, or navigating away by itself
- a transcript making Claude do something the skill's instructions do not ask for, through the script's output
- `open` opening a page that this tool did not generate

Out of scope: what you choose to put in a page and share. The page contains the session as it is; see "Privacy and sharing" in the README.

---

## 日本語

- **対象のバージョン**: 最新のリリースだけ。修正は新しいリリースとして公開する。
- **報告の方法**: セキュリティの問題は **公開の Issue に書かず**、リポジトリの **Security** タブ → **Report a vulnerability**（GitHub の非公開の脆弱性報告）から報告してください。攻撃者に何ができるか（と、その前提条件）、再現手順（できれば架空の履歴で。実際のセッション履歴は送らないでください）、バージョン、OS と Python のバージョンを書いてください。
- 個人で保守しているため対応は可能な範囲になりますが、読んだら返信し、できるだけ早く修正を公開します。
- **対象範囲**: スクリプトが意図しないものを実行する・出力ファイル以外に書き込む、生成したページが自身の `app.js` 以外のスクリプトを実行する・ネットワークから読み込む・勝手に別のページへ移動する、履歴の内容がスクリプトの出力を通じて Claude に skill の指示にない動作をさせる、`open` がこのツールの生成していないページを開く、など。
- **対象外**: ページに何を入れて共有するか。ページにはセッションの内容がそのまま入る（README の「プライバシーと共有」を参照）。
