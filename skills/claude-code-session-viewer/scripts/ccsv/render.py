"""Building the HTML page from parsed transcript items.

The page skeleton, styles and behaviour live in assets/ (page.html, style.css, app.js) and are
inlined into every generated page, so the output stays a single self-contained file.

Placeholders in page.html:
- {{t:<key>}}  a translated string from ccsv/messages/
- {{<NAME>}}   a value computed by render_page() (upper-case names)
- the STYLE and SCRIPT comments are replaced with style.css and app.js
Do not write these placeholder forms anywhere else in the assets (not even in comments):
they would be substituted too.
"""

import base64
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from .i18n import get_lang, t
from .markdown import md_to_html
from .transcript import add_usage, has_usage, image_src, new_usage, usage_input
from .util import esc, fmt_num, fmt_ts, one_line, pre, strip_markdown

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

LONG_CHARS = 900          # messages longer than this are collapsible
LONG_LINES = 18
LONG_TOOLS = 4            # Claude messages with at least this many tool calls are collapsible too
SUMMARY_CHARS = 160
TOC_CHARS = 48

# Messages app.js needs at runtime. They are passed in the page's JSON data block.
JS_MESSAGE_KEYS = ("show_full", "collapse", "toast_downloaded", "toast_copied", "toast_copy_failed")

# {{t:key}} inserts a translated string; {{NAME}} inserts a value computed by render_page().
PLACEHOLDER_RE = re.compile(r"\{\{(t:[a-z_]+|[A-Z_]+)\}\}")


INLINE_SCRIPT_RE = re.compile(r"<script>(.*?)</script>", re.S)


def load_template():
    """page.html with style.css and app.js inlined, placeholders still unfilled.

    Also returns the CSP source ("sha256-...") of the inline script. The page's Content-Security-Policy
    allows only that exact script to run, so markup that slipped through escaping could not run code.
    """
    page = (ASSETS_DIR / "page.html").read_text(encoding="utf-8")
    style = (ASSETS_DIR / "style.css").read_text(encoding="utf-8").rstrip("\n")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8").rstrip("\n")
    page = page.replace("/*{{STYLE}}*/", style).replace("/*{{SCRIPT}}*/", script)
    inline = INLINE_SCRIPT_RE.search(page).group(1)
    digest = base64.b64encode(hashlib.sha256(inline.encode("utf-8")).digest()).decode("ascii")
    return page, "sha256-" + digest


def safe_filename_part(text, limit):
    """Keep letters, digits, "_", "-" and "."; replace everything else with "_".

    The title comes from the transcript, so it must not be able to put shell metacharacters ($, `, ;, ', ...)
    or path separators into the file name that Claude later passes to a command.
    """
    s = re.sub(r"[^\w.-]+", "_", text or "")
    s = re.sub(r"_{2,}", "_", s).strip("._-")[:limit].rstrip("._-")
    return s or "session"


def filter_items(items, include_tools=True, include_thinking=True):
    """Leave tool calls and/or thinking out of the page. Bubbles left with nothing to show are dropped."""
    if include_tools and include_thinking:
        return items
    out = []
    for it in items:
        if it["kind"] == "assistant":
            parts = [p for p in it["parts"]
                     if not (p["type"] == "tool" and not include_tools)
                     and not (p["type"] == "thinking" and not include_thinking)]
            if not parts:
                continue
            it = dict(it, parts=parts)
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# Token usage text
# ---------------------------------------------------------------------------

def fmt_usage(u, detail=False):
    """e.g. "Output 2,345 · Input 45,678 (incl. cache read 44,000)"."""
    breakdown = []
    if u["cache_read"]:
        breakdown.append(t("usage_cache_read", n=fmt_num(u["cache_read"])))
    if detail and u["cache_create"]:
        breakdown.append(t("usage_cache_write", n=fmt_num(u["cache_create"])))
    if breakdown:
        return t("usage_with_breakdown", output=fmt_num(u["output"]), input=fmt_num(usage_input(u)),
                 breakdown=t("usage_separator").join(breakdown))
    return t("usage", output=fmt_num(u["output"]), input=fmt_num(usage_input(u)))


# ---------------------------------------------------------------------------
# Tool calls
# ---------------------------------------------------------------------------

def tool_title(name, inp):
    def g(k):
        v = inp.get(k)
        return v if isinstance(v, str) else ""
    if name == "Bash":
        return g("description") or one_line(g("command"), 90)
    if name in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        return g("file_path") or g("notebook_path")
    if name in ("Grep", "Glob"):
        return g("pattern") + ("  (%s)" % g("path") if g("path") else "")
    if name in ("Agent", "Task"):
        return g("description") + ("  [%s]" % g("subagent_type") if g("subagent_type") else "")
    if name == "Skill":
        return g("skill") + (" " + g("args") if g("args") else "")
    if name == "WebFetch":
        return g("url")
    if name == "WebSearch":
        return g("query")
    if name == "TodoWrite":
        return t("todo_update")
    for k in ("description", "query", "url", "file_path", "path", "command", "prompt"):
        if g(k):
            return one_line(g(k), 90)
    return ""


def tool_input_html(name, inp, has_subagent=False):
    if name == "Bash" and isinstance(inp.get("command"), str):
        return pre("$ " + inp["command"], "cmd")
    if name == "Edit" and "old_string" in inp:
        return '<div class="diff">%s%s</div>' % (pre(inp.get("old_string", ""), "del"), pre(inp.get("new_string", ""), "add"))
    if name == "MultiEdit" and isinstance(inp.get("edits"), list):
        return "".join('<div class="diff">%s%s</div>' % (pre(e.get("old_string", ""), "del"), pre(e.get("new_string", ""), "add"))
                       for e in inp["edits"] if isinstance(e, dict))
    if name == "Write" and isinstance(inp.get("content"), str):
        return fold_block(t("written_content", n=inp["content"].count("\n") + 1), pre(inp["content"]))
    if name == "TodoWrite" and isinstance(inp.get("todos"), list):
        marks = {"completed": "☑", "in_progress": "▶", "pending": "☐"}
        rows = "".join('<li class="todo-%s">%s %s</li>' % (esc(td.get("status")), marks.get(td.get("status"), "•"),
                                                          esc(td.get("content") or td.get("activeForm") or ""))
                       for td in inp["todos"] if isinstance(td, dict))
        return '<ul class="todos">%s</ul>' % rows
    if name in ("Agent", "Task") and isinstance(inp.get("prompt"), str):
        # When the subagent's transcript exists, the prompt is shown as its first bubble instead.
        return "" if has_subagent else fold_block(t("subagent_prompt"), md_to_html(inp["prompt"]))
    if name == "Read":
        extra = {k: v for k, v in inp.items() if k != "file_path"}
        return pre(json.dumps(extra, ensure_ascii=False)) if extra else ""
    if not inp:
        return ""
    return pre(json.dumps(inp, ensure_ascii=False, indent=2), "json")


def tool_result_html(result):
    if result is None:
        return ""
    if isinstance(result, str):
        return pre(result)
    if isinstance(result, list):
        parts = []
        for b in result:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                parts.append(pre(b.get("text", "")))
            elif b.get("type") == "image":
                src = image_src(b)
                if src:
                    parts.append('<img class="shot" src="%s" alt="%s" loading="lazy">' % (esc(src), esc(t("tool_result_image"))))
                else:
                    parts.append('<span class="chip">%s</span>' % esc(t("image")))
            else:
                parts.append(pre(json.dumps(b, ensure_ascii=False)[:2000]))
        return "".join(parts)
    return pre(json.dumps(result, ensure_ascii=False, indent=2))


def result_text_len(result):
    if isinstance(result, str):
        return result.count("\n") + 1
    if isinstance(result, list):
        return sum((b.get("text", "").count("\n") + 1) for b in result if isinstance(b, dict) and b.get("type") == "text")
    return 0


def fold_block(label, inner_html, open_=False, cls=""):
    return '<details class="fold %s"%s><summary>%s</summary><div class="fold-body">%s</div></details>' % (
        esc(cls), " open" if open_ else "", esc(label), inner_html)


def render_tool(part, depth):
    name = part["name"]
    title = tool_title(name, part["input"])
    status = ""
    if part["result"] is None:
        status = '<span class="badge muted">%s</span>' % esc(t("no_result"))
    elif part["is_error"]:
        status = '<span class="badge err">%s</span>' % esc(t("error"))
    body = [tool_input_html(name, part["input"], has_subagent=bool(part.get("subagent")))]
    if part["result"] is not None:
        n = result_text_len(part["result"])
        key = "error_details" if part["is_error"] else "result"
        label = t(key + "_lines", n=n) if n else t(key)
        body.append(fold_block(label, tool_result_html(part["result"]), open_=part["is_error"], cls="result"))
    if part.get("sub_items") is not None:
        _, meta = part["subagent"]
        sub_items = part["sub_items"]
        n_msgs = sum(1 for it in sub_items if it["kind"] in ("user", "assistant"))
        inner = "".join(render_item(it, idx, depth=depth + 1) for idx, it in enumerate(sub_items))
        agent_type = meta.get("agentType", "agent")
        if has_usage(part.get("sub_usage")):
            label = t("subagent_thread_usage", type=agent_type, n=n_msgs, usage=fmt_usage(part["sub_usage"]))
        else:
            label = t("subagent_thread", type=agent_type, n=n_msgs)
        body.append(fold_block(label, '<div class="subthread">%s</div>' % inner, cls="subagent"))
    return ('<details class="tool"><summary><span class="tool-name">%s</span> <span class="tool-title">%s</span>%s</summary>'
            '<div class="tool-body">%s</div></details>') % (esc(name), esc(title), status, "".join(body))


def summarize_tools(parts):
    counts = {}
    for p in parts:
        if p["type"] == "tool":
            counts[p["name"]] = counts.get(p["name"], 0) + 1
    if not counts:
        return ""
    return t("tools_summary", tools=", ".join("%s×%d" % (k, v) if v > 1 else k for k, v in counts.items()))


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def item_summary(item):
    """Summary shown when a message is collapsed and in the table of contents (built mechanically)."""
    if item["kind"] == "user":
        base = strip_markdown(item["text"]) or (t("image_placeholder") if item["attachments"] else "")
        return one_line(base, SUMMARY_CHARS), ""
    texts = [p["text"] for p in item["parts"] if p["type"] == "text"]
    # The last text is usually the conclusion, so use it as the summary.
    base = strip_markdown(texts[-1]) if texts else ""
    tools = summarize_tools(item["parts"])
    if not base:
        events = [p["label"] for p in item["parts"] if p["type"] == "event"]
        base = events[0] if events else t("no_text")
    return one_line(base, SUMMARY_CHARS), tools


def is_long(item):
    if item["kind"] == "user":
        text = item["text"]
        return len(text) > LONG_CHARS or text.count("\n") > LONG_LINES
    texts = "\n".join(p["text"] for p in item["parts"] if p["type"] in ("text", "thinking"))
    tools = sum(1 for p in item["parts"] if p["type"] == "tool")
    return len(texts) > LONG_CHARS or texts.count("\n") > LONG_LINES or tools >= LONG_TOOLS


def render_item(item, idx, depth=0):
    kind = item["kind"]
    ts = fmt_ts(item["ts"])
    if kind == "system":
        body = item["body"]
        if body and not item["body_is_html"]:
            body = esc(body)
        label = esc(item["label"])
        if body:
            inner = '<details class="sys-fold"%s><summary>%s</summary><div class="sys-body">%s</div></details>' % (
                "" if item["fold"] else " open", label, body)
        else:
            inner = '<span class="sys-label">%s</span>' % label
        return '<div class="sys lv-%s"><span class="sys-time">%s</span>%s</div>' % (esc(item["level"]), esc(ts), inner)

    anchor = ' id="m%d"' % idx if depth == 0 else ""
    long_ = is_long(item)
    summary, tools = item_summary(item)
    if kind == "user":
        who = t("you")
        meta_bits = []
        if item.get("tag"):
            meta_bits.append('<span class="badge">%s</span>' % esc(item["tag"]))
        content = [md_to_html(item["text"])] if item["text"] else []
        for att_kind, val in item["attachments"]:
            if att_kind == "image" and val:
                content.append('<img class="shot" src="%s" alt="%s" loading="lazy">' % (esc(val), esc(t("attached_image"))))
            elif att_kind == "image":
                content.append('<span class="chip">%s</span>' % esc(t("image")))
            else:
                content.append('<span class="chip">%s</span>' % esc(t("attachment", name=val)))
        for label, body, foldable in item["notes"]:
            if foldable and body:
                content.append(fold_block(label, pre(body), cls="note"))
            else:
                content.append('<span class="chip">%s: %s</span>' % (esc(label), esc(body)))
    else:
        who = "Claude"
        meta_bits = []
        for m in item["models"]:
            meta_bits.append('<span class="badge model">%s</span>' % esc(m))
        for e in item["efforts"]:
            meta_bits.append('<span class="badge effort">effort: %s</span>' % esc(e))
        content = []
        for p in item["parts"]:
            if p["type"] == "text":
                content.append('<div class="md">%s</div>' % md_to_html(p["text"]))
            elif p["type"] == "thinking":
                content.append(fold_block(t("thinking", n=len(p["text"])), md_to_html(p["text"]), cls="thinking"))
            elif p["type"] == "tool":
                content.append(render_tool(p, depth))
            elif p["type"] == "event":
                if p.get("body"):
                    content.append(fold_block(p["label"], p["body"], cls="event"))
                else:
                    content.append('<div class="chip">%s</div>' % esc(p["label"]))
    fold_html = ""
    cls = "msg %s" % kind
    if long_:
        cls += " long collapsed"
        fold_html = ('<div class="msg-summary"><span class="sum-label">%s</span>%s%s</div>' % (
            esc(t("summary_label")), esc(summary), ' <span class="sum-tools">%s</span>' % esc(tools) if tools else ""))
    toggle = ('<button class="fold-btn" type="button" aria-expanded="false">%s</button>' % esc(t("show_full"))
              if long_ else "")
    # Only Claude's bubbles get an avatar; the user's bubbles stand on their own.
    avatar = "" if kind == "user" else '<div class="avatar">✳</div>'
    return ('<article class="%s"%s data-idx="%d">%s<div class="bubble">'
            '<header><span class="who">%s</span>%s<time>%s</time></header>%s<div class="msg-body">%s</div>%s%s'
            '</div></article>') % (
        cls, anchor, idx, avatar, esc(who), "".join(meta_bits), esc(ts),
        fold_html, "".join(content), turn_tokens_html(item), toggle)


def turn_tokens_html(item):
    """Token usage shown under a Claude bubble. Subagent usage is included in the total and also shown on its own."""
    if item["kind"] != "assistant":
        return ""
    own, sub = item.get("usage"), item.get("sub_usage")
    if not has_usage(own) and not has_usage(sub):
        return ""
    total = add_usage(add_usage(new_usage(), own), sub)
    if has_usage(sub):
        text = t("turn_tokens_with_subagents", usage=fmt_usage(total), sub=fmt_usage(sub))
    else:
        text = t("turn_tokens", usage=fmt_usage(total))
    return '<div class="msg-tokens">%s</div>' % esc(text)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def json_for_script(value):
    """JSON that is safe to put inside a <script> element."""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def render_page(builder, items):
    """Return (html, suggested file name)."""
    m = builder.meta
    title = m["custom_title"] or m["title"] or t("default_title", id=m["session_id"][:8])
    toc = []
    counts = {"user": 0, "assistant": 0}
    for idx, it in enumerate(items):
        if it["kind"] not in ("user", "assistant"):
            continue
        counts[it["kind"]] += 1
        s, tools = item_summary(it)
        label = one_line(s or tools, TOC_CHARS)
        toc.append('<li class="toc-%s"><a href="#m%d"><span class="toc-who">%s</span><span class="toc-text">%s</span>'
                   '<span class="toc-time">%s</span></a></li>' % (
                       it["kind"], idx, "" if it["kind"] == "user" else "✳", esc(label), esc(fmt_ts(it["ts"]))))
    body = "\n".join(render_item(it, idx) for idx, it in enumerate(items))
    period = t("period", start=fmt_ts(m["start"], True), end=fmt_ts(m["end"], True)) if m["start"] else ""
    facts = [
        (t("fact_session_id"), m["session_id"]),
        (t("fact_cwd"), m["cwd"] or ""),
        (t("fact_branch"), m["branch"] or ""),
        (t("fact_period"), period),
        (t("fact_models"), ", ".join(m["models"])),
        (t("fact_messages"), t("messages_count", user=counts["user"], assistant=counts["assistant"])),
        ("Claude Code", m["version"] or ""),
    ]
    facts_html = "".join("<div><dt>%s</dt><dd>%s</dd></div>" % (esc(k), esc(v)) for k, v in facts if v)
    # Token rows are long, so they span the full width.
    total = builder.total_usage()
    if has_usage(total):
        wide = [(t("fact_tokens_total"), esc(fmt_usage(total, detail=True)))]
        if has_usage(builder.sub_usage):
            wide.append((t("fact_tokens_subagents"), esc(fmt_usage(builder.sub_usage, detail=True))))
        if len(builder.usage_by_model) > 1:
            wide.append((t("fact_tokens_by_model"), "<br>".join("%s: %s" % (esc(model), esc(fmt_usage(u)))
                                                                 for model, u in builder.usage_by_model.items())))
        facts_html += "".join('<div class="wide"><dt>%s</dt><dd>%s</dd></div>' % (esc(k), v) for k, v in wide)
    # The language is part of the name so that the Japanese and English pages of a session do not overwrite each other.
    filename = "%s_%s_%s.html" % (safe_filename_part(title, 60), safe_filename_part(m["session_id"][:8], 8), get_lang())
    generated = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    notes = [t("facts_note")] if has_usage(total) else []
    notes.append(t("facts_privacy"))
    template, script_hash = load_template()
    values = {
        "LANG": esc(get_lang()),
        "TITLE": esc(title),
        "SCRIPT_HASH": script_hash,
        "FACTS": facts_html,
        "FACTS_NOTE": "".join('<p class="facts-note">%s</p>' % esc(n) for n in notes),
        "TOC": "".join(toc),
        "BODY": body,
        "FOOTER": esc(t("footer", time=generated)),
        "DATA_JSON": json_for_script({"filename": filename, "messages": {k: t(k) for k in JS_MESSAGE_KEYS}}),
    }

    def fill(mo):
        key = mo.group(1)
        if key.startswith("t:"):
            return esc(t(key[2:]))
        return values.get(key, mo.group(0))

    # Replace everything in one pass, so "{{...}}" inside the transcript is never substituted.
    page = PLACEHOLDER_RE.sub(fill, template)
    return page, filename
