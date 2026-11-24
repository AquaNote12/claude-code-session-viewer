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
    if not s or not isinstance(s, str):
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except (ValueError, OverflowError):
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


# C0/C1 control characters and bidirectional overrides. They can rewrite a terminal's display or
# disguise text, so they are removed from transcript text that is printed to the terminal.
CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f‪-‮⁦-⁩]")


def clean_line(s, limit):
    """Text from a transcript, made safe to print on one terminal line."""
    return one_line(CONTROL_RE.sub(" ", s or ""), limit)


SUMMARY_SOURCE_CHARS = 4000  # a summary is short; after code blocks are replaced, never scan more than this


def replace_code_blocks(s, placeholder):
    """Replace ```...``` pairs with a placeholder, left to right (linear time, unlike a lazy regex)."""
    out, pos = [], 0
    while True:
        start = s.find("```", pos)
        end = s.find("```", start + 3) if start >= 0 else -1
        if end < 0:
            break
        out.append(s[pos:start])
        out.append(" %s " % placeholder)
        pos = end + 3
    out.append(s[pos:])
    return "".join(out)


def strip_markdown(s):
    """Roughly remove Markdown syntax so the text can be used as a summary."""
    s = replace_code_blocks(s or "", t("code_placeholder"))[:SUMMARY_SOURCE_CHARS]
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+", "", s, flags=re.M)
    s = re.sub(r"^\s*\|?[-:| ]+\|?\s*$", "", s, flags=re.M)
    s = s.replace("**", "").replace("__", "").replace("~~", "")
    return s


def load_jsonl(path):
    """Records (dicts) of a JSONL file. Lines that are not a JSON object are skipped."""
    records = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, RecursionError):  # broken or absurdly nested JSON
                continue
            if isinstance(rec, dict):
                records.append(rec)
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
