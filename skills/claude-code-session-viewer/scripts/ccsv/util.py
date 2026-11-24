"""Small helpers shared by the other modules."""

import datetime as dt
import html
import json
import re

from .i18n import t

RESULT_MAX_CHARS = 30000  # display limit per tool result

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def parse_ts(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def fmt_ts(ts, with_date=False):
    if ts is None:
        return ""
    return ts.strftime("%Y-%m-%d %H:%M:%S" if with_date else "%H:%M:%S")


def fmt_num(n):
    return format(n, ",")


def one_line(s, limit):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def strip_markdown(s):
    """Roughly remove Markdown syntax so the text can be used as a summary."""
    s = re.sub(r"```.*?```", " %s " % t("code_placeholder"), s or "", flags=re.S)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+", "", s, flags=re.M)
    s = re.sub(r"^\s*\|?[-:| ]+\|?\s*$", "", s, flags=re.M)
    s = s.replace("**", "").replace("__", "").replace("~~", "")
    return s


def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def pre(text, cls=""):
    """A <pre> block for raw text (command output, tool results, ...), truncated when very long."""
    text = ANSI_RE.sub("", text or "")
    note = ""
    if len(text) > RESULT_MAX_CHARS:
        note = '<div class="trunc">%s</div>' % esc(t("truncated", limit=fmt_num(RESULT_MAX_CHARS),
                                                      total=fmt_num(len(text))))
        text = text[:RESULT_MAX_CHARS]
    return '<pre class="%s">%s</pre>%s' % (esc(cls), esc(text), note)
