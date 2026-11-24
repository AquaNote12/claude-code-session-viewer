"""Finding session files and parsing transcripts.

This is the only module that knows Claude Code's JSONL transcript format. The format is internal
and undocumented, so when a Claude Code update changes it, the fix belongs here.
"""

import json
import os
import re
from pathlib import Path

from .i18n import t
from .markdown import md_to_html
from .util import ANSI_RE, esc, fmt_num, load_jsonl, one_line, parse_ts, pre

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
PROJECTS_DIR = CLAUDE_DIR / "projects"
SUBAGENT_MAX_DEPTH = 2


class SessionLookupError(Exception):
    """The session ID did not match exactly one session file. The message is user-facing."""


# ---------------------------------------------------------------------------
# Finding session files
# ---------------------------------------------------------------------------

def all_session_files():
    if not PROJECTS_DIR.is_dir():
        return []
    return [p for p in PROJECTS_DIR.glob("*/*.jsonl") if p.is_file()]


def project_dir_name(path):
    """Claude Code stores each project's sessions in a directory named after the project path."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def resolve_session(arg):
    p = Path(arg).expanduser()
    if p.suffix == ".jsonl" and p.is_file():
        return p
    hits = [f for f in all_session_files() if f.stem.startswith(arg)]
    if not hits:
        raise SessionLookupError(t("err_not_found", arg=arg, dir=PROJECTS_DIR))
    exact = [f for f in hits if f.stem == arg]
    if exact:
        hits = exact
    if len(hits) > 1:
        lines = "\n".join("  %s" % f for f in hits[:10])
        raise SessionLookupError(t("err_ambiguous") + "\n" + lines)
    return hits[0]


def peek_session(path):
    """Read just the title, the first user prompt and the working directory, for the session list."""
    title = custom = first = None
    cwd = None
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if '"custom-title"' not in line and '"ai-title"' not in line and (first and cwd):
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = d.get("type")
                if kind == "custom-title":
                    custom = d.get("customTitle")
                elif kind == "ai-title":
                    title = d.get("aiTitle")
                if cwd is None and d.get("cwd"):
                    cwd = d["cwd"]
                if first is None and kind == "user" and not d.get("isMeta") and not d.get("isCompactSummary"):
                    texts = user_texts(d)
                    text = clean_prompt_text(" ".join(texts))[0]
                    if text.strip():
                        first = text
    except OSError:
        pass
    return custom or title, first, cwd


# ---------------------------------------------------------------------------
# Record helpers
# ---------------------------------------------------------------------------

def user_texts(rec):
    msg = rec.get("message") or {}
    c = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(c, str):
        return [c]
    if isinstance(c, list):
        return [b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
    return []


PROMPT_TAG_RE = re.compile(r"<(ide_opened_file|ide_selection|system-reminder)>(.*?)</\1>", re.S)


def clean_prompt_text(text):
    """Remove tags injected by the IDE and others; return (text, notes)."""
    notes = []

    def take(m):
        tag, body = m.group(1), m.group(2).strip()
        if tag == "ide_opened_file":
            fm = re.search(r"opened the file (.+?) in the IDE", body)
            notes.append((t("ide_opened_file"), fm.group(1) if fm else body, False))
        elif tag == "ide_selection":
            fm = re.search(r"selected the lines (\d+) to (\d+) from (.+?):", body)
            if fm:
                label = t("ide_selection_range", file=fm.group(3), start=fm.group(1), end=fm.group(2))
            else:
                label = t("ide_selection")
            notes.append((label, body, True))
        return ""

    text = PROMPT_TAG_RE.sub(take, text or "")
    return text.strip(), notes


def tag_value(text, tag):
    m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), text or "", re.S)
    return m.group(1).strip() if m else ""


SAFE_IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")
BASE64_RE = re.compile(r"[A-Za-z0-9+/=\s]+")
HTTP_URL_RE = re.compile(r"https?://", re.I)


def image_src(block):
    """A data: URL for an embedded image, or None.

    Only base64 images of common raster types are embedded. Images given by URL are not loaded:
    the page must not contact other servers when it is opened (that would tell them it was viewed).
    """
    src = block.get("source")
    if not isinstance(src, dict) or src.get("type") != "base64":
        return None
    data, media_type = src.get("data"), src.get("media_type", "image/png")
    if media_type not in SAFE_IMAGE_TYPES or not isinstance(data, str) or not BASE64_RE.fullmatch(data):
        return None
    return "data:%s;base64,%s" % (media_type, re.sub(r"\s+", "", data))


def link_html(url):
    """A link for http(s) URLs; anything else (e.g. javascript:) is shown as plain text."""
    if HTTP_URL_RE.match(url):
        return '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (esc(url), esc(url))
    return esc(url)


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------

USAGE_KEYS = ("input", "cache_create", "cache_read", "output")


def new_usage():
    return dict.fromkeys(USAGE_KEYS, 0)


def add_usage(dst, src):
    for k in USAGE_KEYS:
        dst[k] += src.get(k, 0)
    return dst


def usage_from_api(u):
    """Reduce an API usage object to the four numbers we display."""
    def n(key):
        v = u.get(key)
        return v if isinstance(v, int) else 0
    return {"input": n("input_tokens"), "cache_create": n("cache_creation_input_tokens"),
            "cache_read": n("cache_read_input_tokens"), "output": n("output_tokens")}


def usage_input(u):
    return u["input"] + u["cache_create"] + u["cache_read"]


def has_usage(u):
    return bool(u) and any(u[k] for k in USAGE_KEYS)


# ---------------------------------------------------------------------------
# Transcript -> display items
# ---------------------------------------------------------------------------

class Builder:
    """Read records in order and turn them into a list of items: user bubbles, Claude bubbles and system rows.

    Item shapes (dicts):
      user       kind, ts, text, notes, attachments, tag
      assistant  kind, ts, parts, models, efforts, usage, sub_usage
      system     kind, ts, label, body, body_is_html, level, fold
    A Claude bubble's parts are text, thinking, tool and event dicts.
    """

    def __init__(self, session_path, include_subagents=True, depth=0):
        self.path = Path(session_path)
        self.records = load_jsonl(self.path)
        self.items = []
        self.tools = {}           # tool_use_id -> part
        self.current = None       # Claude bubble being assembled
        self.mode_state = {}
        self.seen_tasks = set()
        self.include_subagents = include_subagents
        self.depth = depth
        self.subagents = self._index_subagents() if include_subagents and depth < SUBAGENT_MAX_DEPTH else {}
        self.meta = {"title": None, "custom_title": None, "cwd": None, "branch": None, "version": None,
                     "session_id": self.path.stem, "start": None, "end": None, "models": [], "prs": []}
        # Token usage. One response is split across several records that carry the same usage,
        # so each message.id is counted once.
        self.seen_usage_ids = set()
        self.usage = new_usage()          # this thread only
        self.sub_usage = new_usage()      # subagents below this thread (including nested ones)
        self.usage_by_model = {}          # per model, including subagents

    def total_usage(self):
        return add_usage(add_usage(new_usage(), self.usage), self.sub_usage)

    def _count_usage(self, model, usage, bubble):
        add_usage(self.usage, usage)
        add_usage(bubble["usage"], usage)
        add_usage(self.usage_by_model.setdefault(model or t("unknown_model"), new_usage()), usage)

    # --- subagents ------------------------------------------------------------
    def _index_subagents(self):
        result = {}
        sub_dir = self.path.with_suffix("") / "subagents"
        if not sub_dir.is_dir():
            return result
        for meta_path in sub_dir.glob("*.meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            jsonl = meta_path.with_name(meta_path.name.replace(".meta.json", ".jsonl"))
            if meta.get("toolUseId") and jsonl.is_file():
                result[meta["toolUseId"]] = (jsonl, meta)
        return result

    def _attach_subagent(self, part, bubble):
        jsonl, _ = part["subagent"]
        sub = Builder(jsonl, include_subagents=True, depth=self.depth + 1)
        part["sub_items"] = sub.build()
        total = sub.total_usage()
        part["sub_usage"] = total
        add_usage(self.sub_usage, total)
        add_usage(bubble["sub_usage"], total)
        for model, u in sub.usage_by_model.items():
            add_usage(self.usage_by_model.setdefault(model, new_usage()), u)

    # --- bubbles --------------------------------------------------------------
    def close_assistant(self):
        if self.current and self.current["parts"]:
            self.items.append(self.current)
        self.current = None

    def assistant(self, ts):
        if self.current is None:
            self.current = {"kind": "assistant", "ts": ts, "parts": [], "models": [], "efforts": [],
                            "usage": new_usage(), "sub_usage": new_usage()}
        return self.current

    def add_system(self, ts, label, body=None, body_is_html=False, level="info", fold=False):
        self.close_assistant()
        self.items.append({"kind": "system", "ts": ts, "label": label, "body": body,
                           "body_is_html": body_is_html, "level": level, "fold": fold})

    def add_event(self, ts, label, body=None, fold=True):
        """A small event shown inside a Claude bubble (e.g. a skill being loaded)."""
        self.assistant(ts)["parts"].append({"type": "event", "label": label, "body": body, "fold": fold})

    def add_user(self, ts, text, notes, attachments, tag=None):
        self.close_assistant()
        self.items.append({"kind": "user", "ts": ts, "text": text, "notes": notes,
                           "attachments": attachments, "tag": tag})

    # --- main loop ------------------------------------------------------------
    def build(self):
        for rec in self.records:
            self._collect_meta(rec)
            kind = rec.get("type")
            ts = parse_ts(rec.get("timestamp"))
            try:
                if kind == "user":
                    self._on_user(rec, ts)
                elif kind == "assistant":
                    self._on_assistant(rec, ts)
                elif kind == "attachment":
                    self._on_attachment(rec, ts)
                elif kind == "system":
                    self._on_system(rec, ts)
                elif kind == "pr-link":
                    url = rec.get("prUrl")
                    if isinstance(url, str) and url and url not in self.meta["prs"]:
                        self.meta["prs"].append(url)
                        self.add_system(ts, t("pr_linked"), link_html(url), body_is_html=True)
            except Exception as e:  # one unreadable record must not stop the whole page
                self.add_system(ts, t("record_error", error=type(e).__name__), level="warn")
        self.close_assistant()
        return self.items

    def _collect_meta(self, rec):
        m = self.meta
        kind = rec.get("type")
        if kind == "ai-title" and rec.get("aiTitle"):
            m["title"] = rec["aiTitle"]
        elif kind == "custom-title" and rec.get("customTitle"):
            m["custom_title"] = rec["customTitle"]
        for key, field in (("cwd", "cwd"), ("branch", "gitBranch"), ("version", "version")):
            if rec.get(field):
                m[key] = rec[field]
        if kind in ("user", "assistant"):
            ts = parse_ts(rec.get("timestamp"))
            if ts:
                m["start"] = m["start"] or ts
                m["end"] = ts

    # --- user records ---------------------------------------------------------
    def _on_user(self, rec, ts):
        msg = rec.get("message") or {}
        content = msg.get("content")
        if rec.get("isCompactSummary"):
            text = content if isinstance(content, str) else "\n".join(user_texts(rec))
            self.add_system(ts, t("compact_summary"), md_to_html(text), body_is_html=True, fold=True)
            return
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]

        # Tool results
        results = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
        for b in results:
            part = self.tools.get(b.get("tool_use_id"))
            if part is not None:
                part["result"] = b.get("content")
                part["is_error"] = bool(b.get("is_error"))
        if results:
            return

        texts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
        joined = "\n".join(texts).strip()

        if rec.get("isMeta"):
            if joined.startswith("Base directory for this skill"):
                first = joined.split("\n", 1)[0]
                name = first.rsplit("/", 1)[-1]
                self.add_event(ts, t("skill_loaded", name=name), md_to_html(joined))
            return  # other meta records (image path notes, local command caveats, ...) are not shown

        if not joined and not any(isinstance(b, dict) and b.get("type") in ("image", "document") for b in blocks):
            return
        if joined.startswith("<command-name>") or joined.startswith("<command-message>"):
            command = ("%s %s" % (tag_value(joined, "command-name"), tag_value(joined, "command-args"))).strip()
            self.add_system(ts, t("command_run", command=command), level="command")
            return
        if joined.startswith("<local-command-stdout>") or joined.startswith("<local-command-stderr>"):
            out = tag_value(joined, "local-command-stdout") or tag_value(joined, "local-command-stderr")
            if out:
                self.add_system(ts, t("command_output"), pre(out), body_is_html=True, level="command",
                                fold=len(out) > 400)
            return
        if joined.startswith("<task-notification>"):
            self._task_notification(joined, ts)
            return
        if re.fullmatch(r"\[Request interrupted by user[^\]]*\]", joined):
            self.add_system(ts, t("interrupted"), level="warn")
            return

        text, notes = clean_prompt_text(joined)
        attachments = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "image":
                attachments.append(("image", image_src(b)))
            elif b.get("type") == "document":
                attachments.append(("document", b.get("title") or t("document")))
        if not text and not attachments:
            # A message that only carries IDE context is kept as a note.
            for label, body, _ in notes:
                self.add_system(ts, label, pre(body) if body else None, body_is_html=True, fold=True)
            return
        self.add_user(ts, text, notes, attachments)

    def _task_notification(self, text, ts):
        task_id = tag_value(text, "task-id")
        if task_id and task_id in self.seen_tasks:
            return
        self.seen_tasks.add(task_id)
        status = tag_value(text, "status")
        summary = tag_value(text, "summary")
        result = tag_value(text, "result")
        label = t("task_notification_status", status=status) if status else t("task_notification")
        if summary:
            label = t("task_notification_summary", label=label, summary=one_line(summary, 120))
        body = md_to_html(result) if result else None
        self.add_system(ts, label, body, body_is_html=True, level="task", fold=True)

    # --- assistant records ----------------------------------------------------
    def _on_assistant(self, rec, ts):
        msg = rec.get("message") or {}
        if rec.get("isApiErrorMessage"):
            text = "\n".join(b.get("text", "") for b in msg.get("content") or [] if isinstance(b, dict))
            self.add_system(ts, t("api_error"), pre(text), body_is_html=True, level="error")
            return
        bubble = self.assistant(ts)
        model = msg.get("model")
        if model and not model.startswith("<") and model not in bubble["models"]:
            bubble["models"].append(model)
            if model not in self.meta["models"]:
                self.meta["models"].append(model)
        effort = rec.get("effort") or rec.get("perTurnEffort")
        if effort and effort not in bubble["efforts"]:
            bubble["efforts"].append(effort)
        msg_id = msg.get("id")
        if isinstance(msg.get("usage"), dict) and msg_id not in self.seen_usage_ids:
            if msg_id:
                self.seen_usage_ids.add(msg_id)
            self._count_usage(model, usage_from_api(msg["usage"]), bubble)
        for b in msg.get("content") or []:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text":
                if b.get("text", "").strip():
                    bubble["parts"].append({"type": "text", "text": b["text"]})
            elif bt == "thinking":
                if b.get("thinking", "").strip():
                    bubble["parts"].append({"type": "thinking", "text": b["thinking"]})
            elif bt in ("tool_use", "server_tool_use"):
                part = {"type": "tool", "id": b.get("id"), "name": b.get("name", "?"),
                        "input": b.get("input") or {}, "result": None, "is_error": False, "subagent": None}
                sub = self.subagents.get(b.get("id"))
                if sub:
                    part["subagent"] = sub
                    self._attach_subagent(part, bubble)
                self.tools[b.get("id")] = part
                bubble["parts"].append(part)
            elif (bt or "").endswith("_tool_result"):
                part = self.tools.get(b.get("tool_use_id"))
                if part is not None:
                    part["result"] = b.get("content")

    # --- attachment records ---------------------------------------------------
    def _on_attachment(self, rec, ts):
        a = rec.get("attachment") or {}
        at = a.get("type")
        if at == "queued_command":
            prompt = a.get("prompt")
            if isinstance(prompt, list):
                text = "\n".join(b.get("text", "") for b in prompt if isinstance(b, dict))
            else:
                text = prompt or ""
            if a.get("commandMode") == "task-notification" or text.lstrip().startswith("<task-notification>"):
                self._task_notification(text, ts)
                return
            text, notes = clean_prompt_text(text)
            if text:
                self.add_user(ts, text, notes, [], tag=t("sent_while_working"))
        elif at == "edited_text_file":
            self.add_system(ts, t("user_edited_file", file=a.get("filename", "")), level="note")
        elif at == "file":
            self.add_system(ts, t("file_attached", file=a.get("displayPath") or a.get("filename", "")), level="note")
        elif at in ("plan_mode", "auto_mode"):
            if not self.mode_state.get(at):
                self.mode_state[at] = True
                self.add_system(ts, t(at + "_enter"), level="mode")
        elif at in ("plan_mode_exit", "auto_mode_exit"):
            key = at[: -len("_exit")]
            if self.mode_state.get(key, True):
                self.mode_state[key] = False
                body = t("plan_file", path=a["planFilePath"]) if a.get("planFilePath") else None
                self.add_system(ts, t(at), pre(body) if body else None, body_is_html=True, level="mode", fold=True)
        elif at in ("hook_success", "hook_error", "hook_blocking_error"):
            stderr = (a.get("stderr") or "").strip()
            exit_code = a.get("exitCode")
            if stderr or (exit_code not in (None, 0)) or at != "hook_success":
                body = "\n".join(x for x in (a.get("stdout", "").strip(), stderr) if x)
                self.add_event(ts, t("hook_event", name=a.get("hookName", ""), code=exit_code),
                               pre(body) if body else None)
        # Everything else (remaining-token notes, tool list deltas, environment info, ...) means little
        # to a human reader and is not shown.

    # --- system records -------------------------------------------------------
    def _on_system(self, rec, ts):
        st = rec.get("subtype")
        content = rec.get("content") or ""
        if st == "compact_boundary":
            cm = rec.get("compactMetadata") or {}
            raw_trigger = cm.get("trigger")
            trigger = {"manual": t("trigger_manual"), "auto": t("trigger_auto")}.get(raw_trigger, raw_trigger or "")
            if trigger and cm.get("preTokens"):
                label = t("compacted_trigger_tokens", trigger=trigger, tokens=fmt_num(cm["preTokens"]))
            elif trigger:
                label = t("compacted_trigger", trigger=trigger)
            else:
                label = t("compacted")
            self.add_system(ts, label, level="compact")
        elif st == "local_command":
            out = tag_value(content, "local-command-stdout") or tag_value(content, "local-command-stderr") or content
            self.add_system(ts, t("command_output"), pre(out), body_is_html=True, level="command",
                            fold=len(out) > 400)
        elif st in ("informational", "api_error", "error", "warning") and content:
            self.add_system(ts, ANSI_RE.sub("", content), level="warn" if st != "informational" else "info")
