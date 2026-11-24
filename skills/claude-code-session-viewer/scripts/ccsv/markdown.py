"""Minimal Markdown-to-HTML converter (no external libraries; input is always escaped)."""

import re

from .util import esc

INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
AUTOLINK_RE = re.compile(r"(?<![\"'=>])(https?://[^\s<>\"')\]]+)")
BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def md_inline(text):
    slots = []

    def keep(fragment):
        slots.append(fragment)
        return "\x00%d\x00" % (len(slots) - 1)

    text = INLINE_CODE_RE.sub(lambda m: keep("<code>%s</code>" % esc(m.group(1))), text)
    text = LINK_RE.sub(
        lambda m: keep('<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(m.group(2)), esc(m.group(1)))),
        text,
    )
    text = AUTOLINK_RE.sub(
        lambda m: keep('<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(m.group(1)), esc(m.group(1)))),
        text,
    )
    text = esc(text)
    text = BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = STRIKE_RE.sub(r"<del>\1</del>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)


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


def md_to_html(src):
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
        if stripped.startswith(">"):
            flush_para()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % md_to_html("\n".join(quote)))
            continue
        if "|" in stripped and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1]):
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
