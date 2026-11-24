"""English messages. This file is the source of truth for every user-visible string.

Rules for all languages:
- Every language defines exactly the same keys with the same {placeholders}
  (tests/test_render_session.py checks this).
- A key ending in "_one" is optional. It is used instead of the base key when n == 1,
  for languages that need a singular form. It may drop {n} but must not add placeholders.
- {n} is always a plain integer; token counts arrive already formatted with thousands separators.
"""

MESSAGES = {
    # --- Command line (--help text, messages printed to the terminal) ---------------------------
    "cli_description": "Convert Claude Code session transcripts into HTML.",
    "cli_list": "list sessions",
    "cli_all": "list sessions from all projects",
    "cli_project": "list sessions of this directory (default: current directory)",
    "cli_current_session": "list sessions of the same project as this session (used when --project is not given)",
    "cli_limit": "maximum number of sessions to list",
    "cli_render": "convert a session into HTML",
    "cli_session": "session ID (a unique prefix is enough) or path to a JSONL file",
    "cli_out": "output file or directory (default: {path})",  # {path}: default output directory
    "cli_no_subagents": "do not include subagent conversations",
    "cli_lang": "language of the output (default: from the OS locale, otherwise English)",
    "err_not_found": "Session not found: {arg} (searched under {dir})",  # {arg}: what the user passed
    "err_ambiguous": "The ID matches more than one session. Please give a longer ID:",  # followed by the matches
    "list_fallback": "(No sessions found for {dir}; listing all projects instead)",
    "untitled": "(untitled)",  # session list: a session without a title or prompt
    "rendered": "Wrote: {path}",
    "source": "Source session: {path}",
    "stats": "Messages: {n} / Size: {kb} KB",  # {kb}: formatted number

    # --- Token usage, e.g. "Output 2,345 · Input 45,678 (incl. cache read 44,000)" --------------
    "usage": "Output {output} · Input {input}",
    "usage_with_breakdown": "Output {output} · Input {input} (incl. {breakdown})",  # {breakdown}: joined items below
    "usage_cache_read": "cache read {n}",
    "usage_cache_write": "cache write {n}",
    "usage_separator": ", ",  # joins the breakdown items
    "unknown_model": "unknown",  # model name when the transcript has none

    # --- Notes attached to user prompts (context the IDE added) -------------------------------
    "ide_opened_file": "File open in the IDE",
    "ide_selection": "Selection in the IDE",
    "ide_selection_range": "Selection in the IDE: {file}:{start}-{end}",

    # --- System rows (centered pills) and events inside Claude's bubbles ----------------------
    "pr_linked": "Linked to a pull request",
    "record_error": "This record could not be displayed ({error})",  # {error}: Python exception class name
    "compact_summary": "Summary of the conversation so far (given to Claude after compaction)",
    "skill_loaded": "Loaded skill: {name}",
    "command_run": "Command: {command}",  # {command}: slash command with its arguments
    "command_output": "Command output",
    "interrupted": "Interrupted by the user",
    "document": "Document",  # fallback title of an attached document
    "task_notification": "Background task notification",
    "task_notification_status": "Background task notification ({status})",  # {status}: e.g. "completed"
    "task_notification_summary": "{label}: {summary}",  # {label}: one of the two keys above
    "api_error": "API error",
    "sent_while_working": "Sent while Claude was working",  # badge on a queued user message
    "user_edited_file": "File edited by the user: {file}",
    "file_attached": "Attached file: {file}",
    "plan_mode_enter": "Entered plan mode",
    "plan_mode_exit": "Exited plan mode",
    "auto_mode_enter": "Entered auto mode",
    "auto_mode_exit": "Exited auto mode",
    "plan_file": "Plan file: {path}",
    "hook_event": "Hook {name} (exit code {code})",
    "compacted": "Conversation compacted",
    "compacted_trigger": "Conversation compacted ({trigger})",  # {trigger}: trigger_manual / trigger_auto
    "compacted_trigger_tokens": "Conversation compacted ({trigger}, {tokens} tokens before)",
    "trigger_manual": "manual",
    "trigger_auto": "automatic",

    # --- Tool call cards ----------------------------------------------------------------------
    "todo_update": "Updated to-dos",  # title of a TodoWrite card
    "written_content": "Written content ({n} lines)",
    "written_content_one": "Written content (1 line)",
    "subagent_prompt": "Instructions to the subagent",
    "tool_result_image": "Image from a tool result",  # alt text
    "no_result": "No result",  # badge: the tool call has no recorded result
    "error": "Error",  # badge: the tool call failed
    "result": "Result",
    "result_lines": "Result ({n} lines)",
    "result_lines_one": "Result (1 line)",
    "error_details": "Error details",
    "error_details_lines": "Error details ({n} lines)",
    "error_details_lines_one": "Error details (1 line)",
    "subagent_thread": "Subagent conversation ({type}, {n} messages)",  # {type}: agent type, e.g. "Explore"
    "subagent_thread_one": "Subagent conversation ({type}, 1 message)",
    "subagent_thread_usage": "Subagent conversation ({type}, {n} messages, {usage})",  # {usage}: token usage text
    "subagent_thread_usage_one": "Subagent conversation ({type}, 1 message, {usage})",
    "tools_summary": "Tools: {tools}",  # {tools}: e.g. "Bash×3, Read"

    # --- Message bubbles ----------------------------------------------------------------------
    "image_placeholder": "[image]",  # summary of a prompt that only has an image
    "code_placeholder": "[code]",  # replaces code blocks in summaries
    "no_text": "(no text)",
    "you": "You",  # name on the user's bubbles
    "attached_image": "Attached image",  # alt text
    "image": "Image",
    "attachment": "Attachment: {name}",
    "thinking": "Thinking ({n} characters)",
    "thinking_one": "Thinking (1 character)",
    "summary_label": "Summary",  # label in front of a collapsed message's summary
    "show_full": "Show all",  # button under a collapsed message (also used by app.js)
    "collapse": "Collapse",  # same button when expanded (also used by app.js)
    "turn_tokens": "Tokens: {usage}",
    "turn_tokens_with_subagents": "Tokens: {usage} / of which subagents: {sub}",
    "truncated": "… Truncated after {limit} characters ({total} characters in total)",

    # --- Page: session facts, toolbar, table of contents, footer -----------------------------
    "default_title": "Claude Code session {id}",  # {id}: first 8 characters of the session ID
    "fact_session_id": "Session ID",
    "fact_cwd": "Working directory",
    "fact_branch": "Branch",
    "fact_period": "Period",
    "period": "{start} – {end}",
    "fact_models": "Models",
    "fact_messages": "Messages",
    "messages_count": "You: {user} / Claude: {assistant}",
    "fact_tokens_total": "Total tokens (including subagents)",
    "fact_tokens_subagents": "Of which subagents",
    "fact_tokens_by_model": "By model",
    "facts_note": ("Token counts are the sum of the API calls recorded in the transcript. Output includes thinking. "
                   "Calls made internally by Claude Code, such as title generation and compaction, are not included."),
    "btn_toc": "Contents",
    "btn_toc_title": "Show or hide the table of contents",  # tooltip
    "toc": "Contents",  # heading of the table of contents
    "btn_expand": "Expand all",
    "btn_collapse": "Collapse long messages",
    "btn_tools": "Tools",
    "btn_thinking": "Thinking",
    "btn_system": "System",
    "btn_copy": "Copy",
    "btn_copy_title": "Copy this HTML to the clipboard",  # tooltip
    "btn_download": "Download",
    "btn_download_title": "Download this HTML",  # tooltip
    "footer": "Generated by claude-code-session-viewer at {time}",
    "toast_downloaded": "Downloaded",  # used by app.js
    "toast_copied": "Copied the HTML to the clipboard",  # used by app.js
    "toast_copy_failed": "Could not copy",  # used by app.js
}
