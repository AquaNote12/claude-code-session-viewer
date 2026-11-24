"""Minimal Markdown-to-HTML converter (no external libraries; input is always escaped)."""

import re

from .util import esc

# The transcript is untrusted input, so every pattern must run in linear time: spans are length-capped
# ({1,500}) so that an opening marker without a closing one cannot make the search rescan the whole line.
INLINE_CODE_RE = re.compile(r"`([^`\n]{1,2000})`")
LINK_RE = re.compile(r"\[([^\[\]\n]{1,500})\]\((https?://[^)\s]{1,2000})\)")
AUTOLINK_RE = re.compile(r"(?<![\"'=>])(https?://[^\s<>\"')\]\ue000\ue001]+)")  # stops at fragment markers
BOLD_RE = re.compile(r"\*\*(?=\S)([^\n]{1,500}?)(?<=\S)\*\*")
STRIKE_RE = re.compile(r"~~(?=\S)([^\n]{1,500}?)(?<=\S)~~")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
TABLE_SEP_CELL_RE = re.compile(r":?-{2,}:?")
MAX_QUOTE_DEPTH = 8

# Placeholders for already-rendered fragments. They are private-use characters, removed from the input first,
# so the input cannot forge a reference to a fragment.
SLOT_OPEN, SLOT_CLOSE = "", ""
SLOT_RE = re.compile(SLOT_OPEN + r"(\d+)" + SLOT_CLOSE)


def md_inline(text):
    slots = []

    def keep(fragment):
        slots.append(fragment)
        return "%s%d%s" % (SLOT_OPEN, len(slots) - 1, SLOT_CLOSE)

    text = text.replace(SLOT_OPEN, "").replace(SLOT_CLOSE, "")
    text = INLINE_CODE_RE.sub(lambda m: keep("<code>%s</code>" % esc(m.group(1))), text)

    def restore(fragment):
        return SLOT_RE.sub(lambda m: slots[int(m.group(1))], fragment)

    def link(m):
        label, url = m.group(1), m.group(2)
        if SLOT_OPEN in url:
            return m.group(0)  # the URL itself contains code: leave it as text
        # The label may contain inline code that was already replaced by a fragment marker; put it back.
        return keep('<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (esc(url), restore(esc(label))))

    text = LINK_RE.sub(link, text)
    text = AUTOLINK_RE.sub(
        lambda m: keep('<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (esc(m.group(1)), esc(m.group(1)))),
        text,
    )
    text = esc(text)
    text = BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = STRIKE_RE.sub(r"<del>\1</del>", text)
    return restore(text)


def is_table_sep(line):
    """True for a table separator row such as "|---|:--:|". Checked cell by cell to stay linear."""
    if "-" not in line:
        return False
    cells = split_row(line)
    return all(TABLE_SEP_CELL_RE.fullmatch(c) for c in cells)


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def render_list(lines):
    """Build ul/ol elements, nested according to indentation."""
    out = []
    stack = []  # (indent, tag). An li stays open until the next item or the end of its nested list.
    for raw in lines:
        m = LIST_RE.match(raw)
        if not m:
            # A continuation line belongs to the item that is still open.
            if stack:
                out.append("<br>" + md_inline(raw.strip()))
            continue
        indent = len(m.group(1).replace("\t", "    "))
        tag = "ol" if m.group(2)[0].isdigit() else "ul"
        body = m.group(3)
        task = re.match(r"\[([ xX])\]\s+(.*)", body)
        if task:
            mark = "☑" if task.group(1).lower() == "x" else "☐"
            body_html = '<span class="task">%s</span> %s' % (mark, md_inline(task.group(2)))
        else:
            body_html = md_inline(body)
        if not stack or indent > stack[-1][0]:
            stack.append((indent, tag))
            out.append("<%s>" % tag)
        else:
            while len(stack) > 1 and indent < stack[-1][0]:
                out.append("</li></%s>" % stack.pop()[1])
            out.append("</li>")
        out.append("<li>%s" % body_html)
    while stack:
        out.append("</li></%s>" % stack.pop()[1])
    return "".join(out)


def md_to_html(src, depth=0):
    src = (src or "").replace("\r\n", "\n")
    lines = src.split("\n")
    out = []
    i = 0
    para = []

    def flush_para():
        if para:
            out.append("<p>%s</p>" % "<br>".join(md_inline(l) for l in para))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        fence = re.match(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)", line)
        if fence:
            flush_para()
            marker = fence.group(1)
            lang = fence.group(2)
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(marker):
                code.append(lines[i])
                i += 1
            i += 1
            label = '<span class="lang">%s</span>' % esc(lang) if lang else ""
            out.append('<pre class="code">%s<code>%s</code></pre>' % (label, esc("\n".join(code))))
            continue
        if not stripped:
            flush_para()
            i += 1
            continue
        h = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if h:
            flush_para()
            level = min(len(h.group(1)) + 2, 6)  # inside a bubble, so start at h3
            out.append("<h%d>%s</h%d>" % (level, md_inline(h.group(2)), level))
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flush_para()
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith(">") and depth < MAX_QUOTE_DEPTH:  # deeper quotes stay plain text
            flush_para()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % md_to_html("\n".join(quote), depth + 1))
            continue
        if "|" in stripped and i + 1 < len(lines) and is_table_sep(lines[i + 1]):
            flush_para()
            head = split_row(lines[i])
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1
            parts = ['<div class="table-wrap"><table><thead><tr>']
            parts += ["<th>%s</th>" % md_inline(c) for c in head]
            parts.append("</tr></thead><tbody>")
            for r in rows:
                parts.append("<tr>%s</tr>" % "".join("<td>%s</td>" % md_inline(c) for c in r))
            parts.append("</tbody></table></div>")
            out.append("".join(parts))
            continue
        if LIST_RE.match(line):
            flush_para()
            block = []
            while i < len(lines):
                cur = lines[i]
                if LIST_RE.match(cur):
                    block.append(cur)
                elif cur.strip() and cur.startswith((" ", "\t")) and block:
                    block.append(cur)
                else:
                    break
                i += 1
            out.append(render_list(block))
            continue
        para.append(line)
        i += 1
    flush_para()
    return "\n".join(out)
