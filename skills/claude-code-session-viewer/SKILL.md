---
name: claude-code-session-viewer
description: Export a Claude Code session transcript to a single standalone HTML page that looks like a chat app, with a table-of-contents sidebar, collapsible long messages, model / effort / token usage per turn, and one-click download and copy. Output in English or Japanese. Use when the user wants to view, keep or share a Claude Code session or conversation history (transcript) as HTML, e.g. "export this session as HTML", "save this conversation as a web page", 「このセッションを HTML にして」, 「セッション履歴を出力して」.
argument-hint: "[session-id | current | list] [--lang en|ja]"
allowed-tools: Bash(python3 *)
license: MIT
---

# Export a Claude Code session to HTML

Convert a session transcript (JSONL under `~/.claude/projects/`) into HTML with the bundled script.
The script does all of the work. Do not Read the JSONL or the generated HTML, and do not write HTML by hand: long sessions would use a lot of tokens and the result would not be consistent.

Script: `${CLAUDE_SKILL_DIR}/scripts/render_session.py`
(If `${CLAUDE_SKILL_DIR}` was not substituted, use `scripts/render_session.py` in the same directory as this SKILL.md. Do not hard-code a path, because it depends on how the skill was installed.)

## Steps

1. Decide which session to export. The arguments are: `$ARGUMENTS`
   - Empty, `current`, "this session", etc. → the current session, `${CLAUDE_SESSION_ID}`
   - `list`, or the target is unclear → run the following, then ask the user which session to export
     ```bash
     python3 "${CLAUDE_SKILL_DIR}/scripts/render_session.py" list --lang <lang>
     ```
     Add `--all` to include sessions from other projects.
   - A session ID (the first 8 characters or so are enough) or a path to a JSONL file → use it as is
2. Decide the output language (`--lang`) in this order:
   1. The user asked for a language explicitly (`--lang en` in the arguments, "in English", 「日本語で」, ...) → use it.
   2. Otherwise, use the language the user is writing in, in this conversation, or the response language configured for Claude Code: Japanese → `ja`, any other language → `en`. Judge by the user's own messages, not by the content of the session being exported (a Japanese-speaking user exporting an English session still gets `ja`).
   3. If there is nothing to go on (for example, a new session whose only input is this command with no arguments, and no language setting), omit `--lang`. The script then uses the OS language, and English if that is unknown.
3. Convert the session.
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/render_session.py" render <session> --lang <lang> [--out <file or directory>]
   ```
   - The default output is `~/Downloads/claude-code-sessions/<title>_<first 8 characters of the ID>.html`. Pass `--out` only when the user names a location.
   - Subagent conversations are included by default. Pass `--no-subagents` if the user does not want them.
4. Tell the user the output path exactly as the script printed it. Ask whether to open it in the browser, and run `open <output path>` if they want.

## Notes

- When exporting the current session, the HTML contains the conversation up to the moment of the export.
- The HTML includes tool results and file contents as they are. Remind the user to check for sensitive information before sharing it.
- If the script reports that the ID matches several sessions or that no session was found, tell the user what it said and confirm the ID.
