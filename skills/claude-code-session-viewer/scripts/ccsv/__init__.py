"""claude-code-session-viewer: turn Claude Code session transcripts into standalone HTML pages.

Modules:
- i18n        current language, message lookup, OS language detection
- messages    user-visible strings, one file per language
- util        small helpers shared by the other modules
- markdown    minimal Markdown-to-HTML converter
- transcript  finding session files and parsing transcripts (knows Claude Code's JSONL format)
- render      building the HTML page from parsed items and the files in assets/
"""
