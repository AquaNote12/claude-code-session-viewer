# claude-code-session-viewer

English | [日本語](README.ja.md)

A Claude Code skill that exports a session transcript to a single standalone HTML page that looks like a chat app.

## Features

- Shows the conversation of a session in chronological order, as chat bubbles.
- Claude's bubbles show the model (e.g. `claude-opus-5-5`) and the effort (e.g. `high`).
- Shows token usage for each Claude bubble and for the whole session (with a per-model breakdown). Output and input are shown separately, and the cache-read part of the input is shown as well. Subagent usage is included in the totals and also shown on its own. Costs are not shown.
- Long messages are collapsed. A collapsed message shows a summary (for Claude: the beginning of its last text and the tools it used).
- A table of contents with one entry per message is shown in a sidebar, and can be turned on and off.
- One click downloads the HTML or copies it to the clipboard.
- Tool calls, thinking and system rows (commands, compaction, mode changes, ...) can be shown or hidden.
- Subagent conversations are shown nested inside the Agent tool call that started them.
- The page can be generated in English or Japanese (see [Language](#language)).
- Supports dark mode and phone-sized screens.

No external libraries or CDNs are used, so the generated HTML also works offline.

## Requirements

- Claude Code (works in both the CLI and the VS Code extension)
- Python 3.9 or later (the `python3` that ships with macOS is fine; no extra packages)

This skill only works with Claude Code. It reads the session transcripts that Claude Code stores (`~/.claude/projects/`) and relies on Claude Code's own substitutions such as `${CLAUDE_SKILL_DIR}`, so it does not work when installed for other agents such as Cursor or Codex.

## Installation

Install it **for your user** (`~/.claude/skills/`) with one of the methods below. A user-level install works in every project, in both the CLI and the VS Code extension.

### Option 1: GitHub CLI (recommended)

Requires GitHub CLI v2.90.0 or later (`gh skill` is a preview feature added in April 2026). Update gh first if it is older.

```bash
gh skill install AquaNote12/claude-code-session-viewer claude-code-session-viewer --agent claude-code --scope user
```

Do not leave out `--agent claude-code --scope user`. Without them, the skill is installed for GitHub Copilot, inside the git repository you are in.

To pin a version, append `@<tag>` to the skill name (e.g. `claude-code-session-viewer@v0.1.0`).

Update:

```bash
gh skill update
```

### Option 2: skills CLI (requires Node.js)

```bash
npx skills add AquaNote12/claude-code-session-viewer --skill claude-code-session-viewer -a claude-code -g
```

Without `-g`, the skill is installed only in the current project.

Update and remove:

```bash
npx skills update claude-code-session-viewer
npx skills remove claude-code-session-viewer
```

### Option 3: Manual

For environments where neither of the above is available. Clone the repository and symlink the skill directory into `~/.claude/skills/`.

```bash
git clone https://github.com/AquaNote12/claude-code-session-viewer.git
ln -s "$(pwd)/claude-code-session-viewer/skills/claude-code-session-viewer" ~/.claude/skills/claude-code-session-viewer
```

To update, run `git pull` in the cloned directory.

### After installing

If the skill does not show up in a Claude Code session that was already open, start a new session.

## Usage

Run it inside Claude Code:

```
/claude-code-session-viewer                # export the current session
/claude-code-session-viewer list           # pick from a list of sessions
/claude-code-session-viewer 1a2b3c4d       # by session ID (a unique prefix is enough)
/claude-code-session-viewer --lang en      # choose the language of the page
```

Asking in plain words, such as "export this session as HTML", also works.

You can also run the script directly (paths are relative to the repository root):

```bash
python3 skills/claude-code-session-viewer/scripts/render_session.py list [--all] [--limit N] [--project DIR | --current-session SESSION] [--lang en|ja]
python3 skills/claude-code-session-viewer/scripts/render_session.py render <session ID | path to JSONL> [--out PATH] [--no-subagents] [--lang en|ja]
```

The default output directory is `~/Downloads/claude-code-sessions/`.

`list` shows the sessions of one project: the one given with `--project`, otherwise the project of the session given with `--current-session` (the skill passes the current session), otherwise the current directory.

## Language

The page (labels, buttons, system rows) and the script's messages are available in English and Japanese. The conversation itself is shown in whatever language it was written in.

Claude chooses the language as follows (Japanese gives `ja`; any other language gives `en`):

| Situation | Language |
|---|---|
| You name a language (`--lang en`, "in English", 「日本語で」, ...) | That language |
| The language of your request matches the response language configured in Claude Code (or, without a setting, the language of the conversation) | That language |
| They differ (e.g. you usually write Japanese but asked in English) | Claude asks you to choose between Japanese and English |
| There is nothing to go on (a new session with only the command, and no language setting) | The OS language (`LC_ALL` / `LC_MESSAGES` / `LANG`, or the system language on macOS), otherwise English |

In non-interactive runs (such as `claude -p`) Claude never asks; it uses the configured response language, then the OS language.

The language is part of the output file name (`..._<session ID>_<lang>.html`), so the Japanese and English pages of a session can sit side by side.

## What is shown

Everything that means something to a human reader is shown; internal bookkeeping is not.

| Shown | Not shown |
|---|---|
| User messages (including messages sent while Claude was working) and attached images | API request records, remaining-token notes |
| Claude's text, and thinking (only when its content was recorded) | Notifications about changes to the tool or skill lists |
| Tool calls and results (Bash commands, Edit diffs, to-do lists, ...) | Automatically added context such as environment info, date and language settings |
| Subagent conversations | File history snapshots |
| Skills being loaded, hook errors | Caveats about local commands, image path notes |
| Slash commands and their output, background task notifications | Empty (encrypted) thinking blocks |
| Compaction and its summary, plan mode and auto mode changes, linked pull requests | |
| Files open and lines selected in the IDE | |

## Caveats

- The JSONL transcript format is internal to Claude Code and not officially documented. A Claude Code update that changes the format may break the page. Unknown record types are skipped.
- By default, Claude Code deletes old session files after a while (`cleanupPeriodDays`).
- Each tool result is truncated to 30,000 characters. Images are embedded in the HTML, so sessions with many images produce large files.
- The HTML contains tool results and file contents as they are. Check for sensitive information before sharing it.
- On pages opened via `file://`, some browsers do not allow the Clipboard API. The copy button then falls back to `document.execCommand("copy")`.

## Development

```
claude-code-session-viewer/
├── skills/
│   └── claude-code-session-viewer/      # the skill itself (this directory is what gets installed)
│       ├── SKILL.md
│       └── scripts/
│           ├── render_session.py        # entry point: command line and language choice
│           └── ccsv/
│               ├── i18n.py              # current language, message lookup, OS language detection
│               ├── messages/            # user-visible strings, one file per language (en.py is the source)
│               ├── util.py              # small shared helpers
│               ├── markdown.py          # minimal Markdown-to-HTML converter
│               ├── transcript.py        # finding sessions and parsing transcripts (Claude Code's JSONL format)
│               ├── render.py            # building the HTML page
│               └── assets/              # page.html, style.css, app.js (inlined into every page)
├── tests/
│   ├── test_render_session.py
│   └── fixtures/                        # a made-up session used by the tests
├── LICENSE
├── README.md
├── README.ja.md
└── .gitignore
```

The `skills/<skill name>/SKILL.md` layout follows the Agent Skills specification. `gh skill install` and `npx skills add` find the skill there.

Run the tests from the repository root:

```bash
python3 -m unittest discover -s tests
```

Where to make a change:

- **Wording**: `ccsv/messages/en.py` (the source, with a comment on what each key is for) and the same key in `ccsv/messages/ja.py`. The tests check that every language has the same keys and placeholders, and that the English page contains no Japanese. To add a language, add a file next to them and register it in `ccsv/messages/__init__.py`.
- **A Claude Code update changed the transcript format**: `ccsv/transcript.py`. It is the only module that reads the JSONL format.
- **Look and behaviour of the page**: `ccsv/assets/` (`page.html`, `style.css`, `app.js`). They are plain HTML, CSS and JavaScript; `app.js` reads the values it needs from the JSON block in the page. Placeholders (`{{...}}`) are only allowed in `page.html`.

## License

[MIT License](LICENSE)
