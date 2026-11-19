#!/usr/bin/env python3
"""Claude Code のセッション履歴 (JSONL) を、単体で開ける HTML に変換する。

使い方:
  render_session.py list [--all] [--limit N] [--project DIR]
  render_session.py render SESSION [--out PATH] [--no-subagents]

SESSION にはセッション ID（先頭一致可）か JSONL ファイルのパスを渡す。
Python 3.9 以上の標準ライブラリだけで動く。
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
PROJECTS_DIR = CLAUDE_DIR / "projects"
DEFAULT_OUT_DIR = Path.home() / "Downloads" / "claude-code-sessions"

LONG_CHARS = 900          # これを超えるメッセージは折り畳み対象
LONG_LINES = 18
LONG_TOOLS = 4            # ツール呼び出しがこれ以上ある Claude メッセージも折り畳み対象
SUMMARY_CHARS = 160
TOC_CHARS = 48
RESULT_MAX_CHARS = 30000  # ツール結果 1 件あたりの表示上限
SUBAGENT_MAX_DEPTH = 2

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# ---------------------------------------------------------------------------
# 汎用ユーティリティ
# ---------------------------------------------------------------------------

def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def parse_ts(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def fmt_ts(t, with_date=False):
    if t is None:
        return ""
    return t.strftime("%Y-%m-%d %H:%M:%S" if with_date else "%H:%M:%S")


def one_line(s, limit):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def strip_markdown(s):
    """概要表示用に Markdown 記号をざっくり落とす。"""
    s = re.sub(r"```.*?```", " [コード] ", s or "", flags=re.S)
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


# ---------------------------------------------------------------------------
# 最小限の Markdown レンダラ（外部ライブラリなし。入力は必ずエスケープする）
# ---------------------------------------------------------------------------

INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
AUTOLINK_RE = re.compile(r"(?<![\"'=>])(https?://[^\s<>\"')\]]+)")
BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")


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


LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def render_list(lines):
    """インデントに応じて入れ子にした ul/ol を作る。"""
    out = []
    stack = []  # (indent, tag)。li は開いたままにしておき、次の項目か入れ子の終わりで閉じる
    for raw in lines:
        m = LIST_RE.match(raw)
        if not m:
            # 継続行は開いている項目に足す
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
            level = min(len(h.group(1)) + 2, 6)  # 吹き出し内なので h3 以下に落とす
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
            t = ['<div class="table-wrap"><table><thead><tr>']
            t += ["<th>%s</th>" % md_inline(c) for c in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>%s</tr>" % "".join("<td>%s</td>" % md_inline(c) for c in r))
            t.append("</tbody></table></div>")
            out.append("".join(t))
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


def pre(text, cls=""):
    text = ANSI_RE.sub("", text or "")
    note = ""
    if len(text) > RESULT_MAX_CHARS:
        note = '<div class="trunc">… 長いため %s 文字以降を省略しました（全 %s 文字）</div>' % (
            format(RESULT_MAX_CHARS, ","), format(len(text), ","))
        text = text[:RESULT_MAX_CHARS]
    return '<pre class="%s">%s</pre>%s' % (esc(cls), esc(text), note)


# ---------------------------------------------------------------------------
# セッションファイルの探索
# ---------------------------------------------------------------------------

def all_session_files():
    if not PROJECTS_DIR.is_dir():
        return []
    return [p for p in PROJECTS_DIR.glob("*/*.jsonl") if p.is_file()]


def project_dir_name(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def resolve_session(arg):
    p = Path(arg).expanduser()
    if p.suffix == ".jsonl" and p.is_file():
        return p
    hits = [f for f in all_session_files() if f.stem.startswith(arg)]
    if not hits:
        sys.exit("セッションが見つかりません: %s（%s 配下を検索しました）" % (arg, PROJECTS_DIR))
    exact = [f for f in hits if f.stem == arg]
    if exact:
        hits = exact
    if len(hits) > 1:
        lines = "\n".join("  %s" % f for f in hits[:10])
        sys.exit("ID が複数のセッションに一致しました。もっと長く指定してください:\n" + lines)
    return hits[0]


def peek_session(path):
    """一覧表示用に、タイトルと最初のユーザー発言だけを拾う。"""
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
                t = d.get("type")
                if t == "custom-title":
                    custom = d.get("customTitle")
                elif t == "ai-title":
                    title = d.get("aiTitle")
                if cwd is None and d.get("cwd"):
                    cwd = d["cwd"]
                if first is None and t == "user" and not d.get("isMeta") and not d.get("isCompactSummary"):
                    texts = user_texts(d)
                    text = clean_prompt_text(" ".join(texts))[0]
                    if text.strip():
                        first = text
    except OSError:
        pass
    return custom or title, first, cwd


def cmd_list(args):
    files = all_session_files()
    if not args.all:
        target = project_dir_name(Path(args.project or os.getcwd()).resolve())
        scoped = [f for f in files if f.parent.name == target]
        if scoped:
            files = scoped
        else:
            print("（%s のセッションが無いため、全プロジェクトを表示します）" % (args.project or os.getcwd()))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[: args.limit]:
        title, first, cwd = peek_session(f)
        mtime = dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print("%s  %s  %s" % (f.stem, mtime, one_line(title or first or "(タイトルなし)", 60)))
        if args.all or cwd:
            print("    cwd: %s" % (cwd or f.parent.name))


# ---------------------------------------------------------------------------
# JSONL → 表示用アイテム
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
    """IDE などが差し込むタグを本文から外し、(本文, 補足リスト) を返す。"""
    notes = []

    def take(m):
        tag, body = m.group(1), m.group(2).strip()
        if tag == "ide_opened_file":
            fm = re.search(r"opened the file (.+?) in the IDE", body)
            notes.append(("IDE で開いていたファイル", fm.group(1) if fm else body, False))
        elif tag == "ide_selection":
            fm = re.search(r"selected the lines (\d+) to (\d+) from (.+?):", body)
            label = "IDE で選択した範囲"
            if fm:
                label += ": %s:%s-%s" % (fm.group(3), fm.group(1), fm.group(2))
            notes.append((label, body, True))
        return ""

    text = PROMPT_TAG_RE.sub(take, text or "")
    return text.strip(), notes


USAGE_KEYS = ("input", "cache_create", "cache_read", "output")


def new_usage():
    return dict.fromkeys(USAGE_KEYS, 0)


def add_usage(dst, src):
    for k in USAGE_KEYS:
        dst[k] += src.get(k, 0)
    return dst


def usage_from_api(u):
    """API の usage を、表示用の 4 項目にまとめる。"""
    def n(key):
        v = u.get(key)
        return v if isinstance(v, int) else 0
    return {"input": n("input_tokens"), "cache_create": n("cache_creation_input_tokens"),
            "cache_read": n("cache_read_input_tokens"), "output": n("output_tokens")}


def usage_input(u):
    return u["input"] + u["cache_create"] + u["cache_read"]


def has_usage(u):
    return bool(u) and any(u[k] for k in USAGE_KEYS)


def fmt_usage(u, detail=False):
    """例: 出力 2,345 ・ 入力 45,678（うちキャッシュ読込 44,000）"""
    s = "出力 %s ・ 入力 %s" % (format(u["output"], ","), format(usage_input(u), ","))
    inner = []
    if u["cache_read"]:
        inner.append("キャッシュ読込 %s" % format(u["cache_read"], ","))
    if detail and u["cache_create"]:
        inner.append("キャッシュ作成 %s" % format(u["cache_create"], ","))
    if inner:
        s += "（うち%s）" % " ・ ".join(inner)
    return s


def tag_value(text, tag):
    m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), text or "", re.S)
    return m.group(1).strip() if m else ""


class Builder:
    """レコードを順に読んで、吹き出し・システム行のリストを作る。"""

    def __init__(self, session_path, include_subagents=True, depth=0):
        self.path = Path(session_path)
        self.records = load_jsonl(self.path)
        self.items = []
        self.tools = {}           # tool_use_id -> part
        self.current = None       # 組み立て中の Claude 吹き出し
        self.mode_state = {}
        self.seen_tasks = set()
        self.include_subagents = include_subagents
        self.depth = depth
        self.subagents = self._index_subagents() if include_subagents and depth < SUBAGENT_MAX_DEPTH else {}
        self.meta = {"title": None, "custom_title": None, "cwd": None, "branch": None, "version": None,
                     "session_id": self.path.stem, "start": None, "end": None, "models": [], "prs": []}
        # トークン数。1 つの応答が複数レコードに分かれて同じ usage を持つので、message.id で重複を除く
        self.seen_usage_ids = set()
        self.usage = new_usage()          # このスレッド自身の分
        self.sub_usage = new_usage()      # 配下のサブエージェントの分（入れ子も含む）
        self.usage_by_model = {}          # サブエージェントの分も含めたモデル別

    def total_usage(self):
        return add_usage(add_usage(new_usage(), self.usage), self.sub_usage)

    def _count_usage(self, model, usage, bubble):
        add_usage(self.usage, usage)
        add_usage(bubble["usage"], usage)
        add_usage(self.usage_by_model.setdefault(model or "不明", new_usage()), usage)

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

    # --- サブエージェント ----------------------------------------------------
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

    # --- 吹き出しの管理 ------------------------------------------------------
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
        """Claude 吹き出しの中に入れる小さなイベント（Skill 読み込みなど）。"""
        self.assistant(ts)["parts"].append({"type": "event", "label": label, "body": body, "fold": fold})

    def add_user(self, ts, text, notes, attachments, tag=None):
        self.close_assistant()
        self.items.append({"kind": "user", "ts": ts, "text": text, "notes": notes,
                           "attachments": attachments, "tag": tag})

    # --- メイン処理 ----------------------------------------------------------
    def build(self):
        for rec in self.records:
            self._collect_meta(rec)
            t = rec.get("type")
            ts = parse_ts(rec.get("timestamp"))
            try:
                if t == "user":
                    self._on_user(rec, ts)
                elif t == "assistant":
                    self._on_assistant(rec, ts)
                elif t == "attachment":
                    self._on_attachment(rec, ts)
                elif t == "system":
                    self._on_system(rec, ts)
                elif t == "pr-link":
                    url = rec.get("prUrl")
                    if url and url not in self.meta["prs"]:
                        self.meta["prs"].append(url)
                        self.add_system(ts, "Pull Request と紐付きました",
                                        '<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(url), esc(url)),
                                        body_is_html=True)
            except Exception as e:  # 1 レコードの解釈失敗で全体を止めない
                self.add_system(ts, "このレコードは表示できませんでした (%s)" % type(e).__name__, level="warn")
        self.close_assistant()
        return self.items

    def _collect_meta(self, rec):
        m = self.meta
        t = rec.get("type")
        if t == "ai-title" and rec.get("aiTitle"):
            m["title"] = rec["aiTitle"]
        elif t == "custom-title" and rec.get("customTitle"):
            m["custom_title"] = rec["customTitle"]
        for key, field in (("cwd", "cwd"), ("branch", "gitBranch"), ("version", "version")):
            if rec.get(field):
                m[key] = rec[field]
        if t in ("user", "assistant"):
            ts = parse_ts(rec.get("timestamp"))
            if ts:
                m["start"] = m["start"] or ts
                m["end"] = ts

    # --- user レコード -------------------------------------------------------
    def _on_user(self, rec, ts):
        msg = rec.get("message") or {}
        content = msg.get("content")
        if rec.get("isCompactSummary"):
            text = content if isinstance(content, str) else "\n".join(user_texts(rec))
            self.add_system(ts, "これまでの会話の要約（圧縮後に Claude へ渡された内容）",
                            md_to_html(text), body_is_html=True, fold=True)
            return
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]

        # ツール結果
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
                self.add_event(ts, "Skill を読み込み: %s" % name, md_to_html(joined))
            return  # それ以外のメタ情報（画像パス注記、ローカルコマンドの注意書きなど）は出さない

        if not joined and not any(isinstance(b, dict) and b.get("type") in ("image", "document") for b in blocks):
            return
        if joined.startswith("<command-name>") or joined.startswith("<command-message>"):
            name = tag_value(joined, "command-name")
            cmd_args = tag_value(joined, "command-args")
            self.add_system(ts, "コマンド実行: %s %s" % (name, cmd_args), level="command")
            return
        if joined.startswith("<local-command-stdout>") or joined.startswith("<local-command-stderr>"):
            out = tag_value(joined, "local-command-stdout") or tag_value(joined, "local-command-stderr")
            if out:
                self.add_system(ts, "コマンドの出力", pre(out), body_is_html=True, level="command",
                                fold=len(out) > 400)
            return
        if joined.startswith("<task-notification>"):
            self._task_notification(joined, ts)
            return
        if re.fullmatch(r"\[Request interrupted by user[^\]]*\]", joined):
            self.add_system(ts, "ユーザーが処理を中断しました", level="warn")
            return

        text, notes = clean_prompt_text(joined)
        attachments = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "image":
                attachments.append(("image", image_src(b)))
            elif b.get("type") == "document":
                attachments.append(("document", b.get("title") or "ドキュメント"))
        if not text and not attachments:
            # IDE 情報だけのメッセージは補足として残す
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
        label = "バックグラウンドタスク通知%s" % ("（%s）" % status if status else "")
        if summary:
            label += ": " + one_line(summary, 120)
        body = md_to_html(result) if result else None
        self.add_system(ts, label, body, body_is_html=True, level="task", fold=True)

    # --- assistant レコード --------------------------------------------------
    def _on_assistant(self, rec, ts):
        msg = rec.get("message") or {}
        if rec.get("isApiErrorMessage"):
            text = "\n".join(b.get("text", "") for b in msg.get("content") or [] if isinstance(b, dict))
            self.add_system(ts, "API エラー", pre(text), body_is_html=True, level="error")
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

    # --- attachment レコード -------------------------------------------------
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
                self.add_user(ts, text, notes, [], tag="Claude の作業中に送信")
        elif at == "edited_text_file":
            self.add_system(ts, "ユーザーがファイルを編集: %s" % a.get("filename", ""), level="note")
        elif at == "file":
            self.add_system(ts, "ファイルを添付: %s" % (a.get("displayPath") or a.get("filename", "")), level="note")
        elif at in ("plan_mode", "auto_mode"):
            if not self.mode_state.get(at):
                self.mode_state[at] = True
                self.add_system(ts, {"plan_mode": "プランモードに入りました", "auto_mode": "オートモードに入りました"}[at],
                                level="mode")
        elif at in ("plan_mode_exit", "auto_mode_exit"):
            key = at[: -len("_exit")]
            if self.mode_state.get(key, True):
                self.mode_state[key] = False
                label = {"plan_mode": "プランモードを終了しました", "auto_mode": "オートモードを終了しました"}[key]
                body = None
                if a.get("planFilePath"):
                    body = "プランファイル: %s" % a["planFilePath"]
                self.add_system(ts, label, pre(body) if body else None, body_is_html=True, level="mode", fold=True)
        elif at == "hook_success" or at == "hook_error" or at == "hook_blocking_error":
            stderr = (a.get("stderr") or "").strip()
            exit_code = a.get("exitCode")
            if stderr or (exit_code not in (None, 0)) or at != "hook_success":
                body = "\n".join(x for x in (a.get("stdout", "").strip(), stderr) if x)
                self.add_event(ts, "フック %s（終了コード %s）" % (a.get("hookName", ""), exit_code),
                               pre(body) if body else None)
        # それ以外（トークン残量の注記、ツール一覧の差分、環境情報など）は人が読んでも意味が薄いので出さない

    # --- system レコード -----------------------------------------------------
    def _on_system(self, rec, ts):
        st = rec.get("subtype")
        content = rec.get("content") or ""
        if st == "compact_boundary":
            cm = rec.get("compactMetadata") or {}
            trig = {"manual": "手動", "auto": "自動"}.get(cm.get("trigger"), cm.get("trigger") or "")
            label = "会話を圧縮しました"
            if trig:
                label += "（%s" % trig
                if cm.get("preTokens"):
                    label += "・圧縮前 %s トークン" % format(cm["preTokens"], ",")
                label += "）"
            self.add_system(ts, label, level="compact")
        elif st == "local_command":
            out = tag_value(content, "local-command-stdout") or tag_value(content, "local-command-stderr") or content
            self.add_system(ts, "コマンドの出力", pre(out), body_is_html=True, level="command", fold=len(out) > 400)
        elif st in ("informational", "api_error", "error", "warning") and content:
            self.add_system(ts, ANSI_RE.sub("", content), level="warn" if st != "informational" else "info")


def image_src(block):
    src = block.get("source") or {}
    if src.get("type") == "base64" and src.get("data"):
        return "data:%s;base64,%s" % (src.get("media_type", "image/png"), src["data"])
    if src.get("type") == "url":
        return src.get("url")
    return None


# ---------------------------------------------------------------------------
# HTML 生成
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
        return "ToDo を更新"
    for k in ("description", "query", "url", "file_path", "path", "command", "prompt"):
        if g(k):
            return one_line(g(k), 90)
    return ""


def tool_input_html(name, inp, has_subagent=False):
    if name == "Bash" and isinstance(inp.get("command"), str):
        return pre("$ " + inp["command"], "cmd")
    if name == "Edit" and "old_string" in inp:
        return ('<div class="diff">%s%s</div>' % (pre(inp.get("old_string", ""), "del"), pre(inp.get("new_string", ""), "add")))
    if name == "MultiEdit" and isinstance(inp.get("edits"), list):
        return "".join('<div class="diff">%s%s</div>' % (pre(e.get("old_string", ""), "del"), pre(e.get("new_string", ""), "add"))
                       for e in inp["edits"] if isinstance(e, dict))
    if name == "Write" and isinstance(inp.get("content"), str):
        return fold_block("書き込んだ内容（%d 行）" % (inp["content"].count("\n") + 1), pre(inp["content"]))
    if name == "TodoWrite" and isinstance(inp.get("todos"), list):
        marks = {"completed": "☑", "in_progress": "▶", "pending": "☐"}
        rows = "".join('<li class="todo-%s">%s %s</li>' % (esc(t.get("status")), marks.get(t.get("status"), "・"),
                                                          esc(t.get("content") or t.get("activeForm") or ""))
                       for t in inp["todos"] if isinstance(t, dict))
        return '<ul class="todos">%s</ul>' % rows
    if name in ("Agent", "Task") and isinstance(inp.get("prompt"), str):
        # やり取りが残っていれば、指示はその最初の吹き出しとして表示される
        return "" if has_subagent else fold_block("サブエージェントへの指示", md_to_html(inp["prompt"]))
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
                    parts.append('<img class="shot" src="%s" alt="ツール結果の画像" loading="lazy">' % esc(src))
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
        status = '<span class="badge muted">結果なし</span>'
    elif part["is_error"]:
        status = '<span class="badge err">エラー</span>'
    body = [tool_input_html(name, part["input"], has_subagent=bool(part.get("subagent")))]
    if part["result"] is not None:
        n = result_text_len(part["result"])
        label = ("エラー内容" if part["is_error"] else "結果") + ("（%d 行）" % n if n else "")
        body.append(fold_block(label, tool_result_html(part["result"]), open_=part["is_error"], cls="result"))
    if part.get("sub_items") is not None:
        _, meta = part["subagent"]
        sub_items = part["sub_items"]
        n_msgs = sum(1 for it in sub_items if it["kind"] in ("user", "assistant"))
        inner = "".join(render_item(it, idx, depth=depth + 1) for idx, it in enumerate(sub_items))
        label = "サブエージェントのやり取り（%s・%d 件" % (meta.get("agentType", "agent"), n_msgs)
        if has_usage(part.get("sub_usage")):
            label += "・" + fmt_usage(part["sub_usage"])
        body.append(fold_block(label + "）", '<div class="subthread">%s</div>' % inner, cls="subagent"))
    return ('<details class="tool"><summary><span class="tool-name">%s</span> <span class="tool-title">%s</span>%s</summary>'
            '<div class="tool-body">%s</div></details>') % (esc(name), esc(title), status, "".join(body))


def summarize_tools(parts):
    counts = {}
    for p in parts:
        if p["type"] == "tool":
            counts[p["name"]] = counts.get(p["name"], 0) + 1
    if not counts:
        return ""
    return "ツール " + ", ".join("%s×%d" % (k, v) if v > 1 else k for k, v in counts.items())


def item_summary(item):
    """折り畳み時と目次に出す概要（機械的に作る）。"""
    if item["kind"] == "user":
        base = strip_markdown(item["text"]) or ("[画像]" if item["attachments"] else "")
        return one_line(base, SUMMARY_CHARS), ""
    texts = [p["text"] for p in item["parts"] if p["type"] == "text"]
    # 最後のテキストが結論であることが多いので、それを概要にする
    base = strip_markdown(texts[-1]) if texts else ""
    tools = summarize_tools(item["parts"])
    if not base:
        events = [p["label"] for p in item["parts"] if p["type"] == "event"]
        base = events[0] if events else "（テキストなし）"
    return one_line(base, SUMMARY_CHARS), tools


def is_long(item):
    if item["kind"] == "user":
        t = item["text"]
        return len(t) > LONG_CHARS or t.count("\n") > LONG_LINES
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
        who = "あなた"
        meta_bits = []
        if item.get("tag"):
            meta_bits.append('<span class="badge">%s</span>' % esc(item["tag"]))
        content = [md_to_html(item["text"])] if item["text"] else []
        for kind_, val in item["attachments"]:
            if kind_ == "image" and val:
                content.append('<img class="shot" src="%s" alt="添付画像" loading="lazy">' % esc(val))
            elif kind_ == "image":
                content.append('<span class="chip">画像</span>')
            else:
                content.append('<span class="chip">添付: %s</span>' % esc(val))
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
                content.append(fold_block("思考（%d 文字）" % len(p["text"]), md_to_html(p["text"]), cls="thinking"))
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
        fold_html = ('<div class="msg-summary"><span class="sum-label">概要</span>%s%s</div>' % (
            esc(summary), ' <span class="sum-tools">%s</span>' % esc(tools) if tools else ""))
    toggle = '<button class="fold-btn" type="button" aria-expanded="false">全文を表示</button>' if long_ else ""
    # アバターは Claude 側だけに付ける（ユーザー側は吹き出しのみ）
    avatar = "" if kind == "user" else '<div class="avatar">✳</div>'
    return ('<article class="%s"%s data-idx="%d">%s<div class="bubble">'
            '<header><span class="who">%s</span>%s<time>%s</time></header>%s<div class="msg-body">%s</div>%s%s'
            '</div></article>') % (
        cls, anchor, idx, avatar, who, "".join(meta_bits), esc(ts),
        fold_html, "".join(content), turn_tokens_html(item), toggle)


def turn_tokens_html(item):
    """Claude の吹き出しの下に出すトークン数。サブエージェントの分は合計に含めて内訳を併記する。"""
    if item["kind"] != "assistant":
        return ""
    own, sub = item.get("usage"), item.get("sub_usage")
    if not has_usage(own) and not has_usage(sub):
        return ""
    total = add_usage(add_usage(new_usage(), own), sub)
    text = "トークン: " + fmt_usage(total)
    if has_usage(sub):
        text += " ／ うちサブエージェント: " + fmt_usage(sub)
    return '<div class="msg-tokens">%s</div>' % esc(text)


def render_page(builder, items):
    m = builder.meta
    title = m["custom_title"] or m["title"] or "Claude Code セッション %s" % m["session_id"][:8]
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
    facts = [
        ("セッション ID", m["session_id"]),
        ("作業ディレクトリ", m["cwd"] or ""),
        ("ブランチ", m["branch"] or ""),
        ("期間", "%s 〜 %s" % (fmt_ts(m["start"], True), fmt_ts(m["end"], True)) if m["start"] else ""),
        ("モデル", ", ".join(m["models"])),
        ("メッセージ数", "あなた %d 件 / Claude %d 件" % (counts["user"], counts["assistant"])),
        ("Claude Code", m["version"] or ""),
    ]
    facts_html = "".join("<div><dt>%s</dt><dd>%s</dd></div>" % (esc(k), esc(v)) for k, v in facts if v)
    # トークン数は文が長いので、横幅いっぱいの行で表示する
    total = builder.total_usage()
    if has_usage(total):
        wide = [("トークン合計（サブエージェントを含む）", esc(fmt_usage(total, detail=True)))]
        if has_usage(builder.sub_usage):
            wide.append(("うちサブエージェント", esc(fmt_usage(builder.sub_usage, detail=True))))
        if len(builder.usage_by_model) > 1:
            wide.append(("モデル別", "<br>".join("%s: %s" % (esc(model), esc(fmt_usage(u)))
                                                 for model, u in builder.usage_by_model.items())))
        facts_html += "".join('<div class="wide"><dt>%s</dt><dd>%s</dd></div>' % (esc(k), v) for k, v in wide)
    filename = re.sub(r"[\\/:*?\"<>|\s]+", "_", title).strip("_")[:60] + "_%s.html" % m["session_id"][:8]
    generated = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    values = {
        "TITLE": esc(title),
        "FILENAME_JS": json.dumps(filename, ensure_ascii=False).replace("</", "<\\/"),
        "FACTS": facts_html,
        "FACTS_NOTE": ('<p class="facts-note">トークン数は履歴に記録された API 呼び出しの合計です。出力には思考を含みます。'
                       'タイトルの自動生成や会話の圧縮など、Claude Code が内部で行う呼び出しは含みません。</p>'
                       if has_usage(total) else ""),
        "TOC": "".join(toc),
        "BODY": body,
        "GENERATED": esc(generated),
    }
    # 1 回の走査で置換する（本文に {{...}} が含まれていても二重に置換しない）
    page = re.sub(r"\{\{([A-Z_]+)\}\}", lambda mo: values.get(mo.group(1), mo.group(0)), TEMPLATE)
    return page, filename


def cmd_render(args):
    path = resolve_session(args.session)
    builder = Builder(path, include_subagents=not args.no_subagents)
    items = builder.build()
    page, filename = render_page(builder, items)
    out = Path(args.out).expanduser() if args.out else DEFAULT_OUT_DIR / filename
    if out.is_dir():
        out = out / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    n = sum(1 for it in items if it["kind"] in ("user", "assistant"))
    print("出力しました: %s" % out)
    print("元のセッション: %s" % path)
    print("メッセージ %d 件 / %s KB" % (n, format(len(page.encode("utf-8")) // 1024, ",")))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root {
  --bg: #f4f5f7; --panel: #ffffff; --text: #1d2129; --muted: #6b7280; --line: #e3e5e8;
  --user-bg: #2f6fed; --user-text: #ffffff; --ai-bg: #ffffff; --ai-border: #e3e5e8;
  --accent: #c96442; --code-bg: #f3f4f6; --chip-bg: #eef0f3; --err: #c0392b; --ok: #1e8e3e;
  --add-bg: #e8f5ea; --del-bg: #fdecea; --sys-text: #6b7280; --shadow: 0 1px 2px rgba(0,0,0,.06);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #15171b; --panel: #1d2026; --text: #e6e8eb; --muted: #9aa1ab; --line: #2c3038;
    --user-bg: #3b6fd9; --user-text: #ffffff; --ai-bg: #1f232a; --ai-border: #2c3038;
    --accent: #e08a6b; --code-bg: #262a31; --chip-bg: #2a2e36; --err: #ff7b6b; --ok: #6bd18a;
    --add-bg: #1e3326; --del-bg: #3a2222; --sys-text: #9aa1ab; --shadow: none;
  }
}
:root[data-theme="dark"] {
  --bg: #15171b; --panel: #1d2026; --text: #e6e8eb; --muted: #9aa1ab; --line: #2c3038;
  --user-bg: #3b6fd9; --user-text: #ffffff; --ai-bg: #1f232a; --ai-border: #2c3038;
  --accent: #e08a6b; --code-bg: #262a31; --chip-bg: #2a2e36; --err: #ff7b6b; --ok: #6bd18a;
  --add-bg: #1e3326; --del-bg: #3a2222; --sys-text: #9aa1ab; --shadow: none;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 72px; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.65 -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", "Segoe UI", sans-serif; }
a { color: var(--user-bg); }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px; }

/* ツールバー */
.topbar { position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; background: var(--panel); border-bottom: 1px solid var(--line); }
.topbar h1 { font-size: 15px; margin: 0; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.btn { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 8px;
  padding: 5px 10px; font-size: 12.5px; cursor: pointer; white-space: nowrap; }
.btn:hover { border-color: var(--muted); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn[aria-pressed="true"] { background: var(--chip-bg); }
.btn-group { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; min-width: 0; }

/* レイアウト */
.layout { display: flex; align-items: flex-start; }
.toc { position: sticky; top: 53px; width: 280px; flex: none; height: calc(100vh - 53px); overflow-y: auto;
  border-right: 1px solid var(--line); background: var(--panel); padding: 8px 0; }
body.toc-off .toc { display: none; }
.toc h2 { font-size: 12px; color: var(--muted); margin: 4px 14px 8px; font-weight: 600; }
.toc ol { list-style: none; margin: 0; padding: 0; }
.toc a { display: grid; grid-template-columns: 20px 1fr auto; gap: 6px; padding: 5px 12px; color: var(--text);
  text-decoration: none; font-size: 12.5px; border-left: 3px solid transparent; }
.toc a:hover { background: var(--chip-bg); }
.toc a.active { border-left-color: var(--accent); background: var(--chip-bg); }
.toc-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.toc-time { color: var(--muted); font-size: 11px; }
.toc-user .toc-text { color: var(--user-bg); }
main { flex: 1; min-width: 0; padding: 16px 16px 80px; }
.layout, .thread { min-width: 0; max-width: 100%; }
body { overflow-x: hidden; }
.thread { max-width: 940px; margin: 0 auto; }

/* セッション情報 */
.facts { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; margin-bottom: 20px; }
.facts dl { margin: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 4px 20px; }
.facts dt { color: var(--muted); font-size: 11.5px; }
.facts dd { margin: 0 0 4px; overflow-wrap: anywhere; }
.facts .wide { grid-column: 1 / -1; }
.facts-note { margin: 6px 0 0; font-size: 11.5px; color: var(--muted); }
.msg-tokens { margin-top: 6px; padding-top: 4px; border-top: 1px dashed var(--line); font-size: 11.5px; color: var(--muted); }

/* 吹き出し */
.msg { display: flex; gap: 10px; margin: 14px 0; align-items: flex-start; }
.msg > .avatar { width: 32px; height: 32px; border-radius: 50%; flex: none; display: grid; place-items: center;
  font-size: 16px; background: var(--chip-bg); }
.msg.assistant > .avatar { background: var(--accent); color: #fff; font-size: 18px; }
.msg.user { flex-direction: row-reverse; }
.bubble { min-width: 0; max-width: min(760px, 88%); border-radius: 16px; padding: 10px 14px; box-shadow: var(--shadow); }
.msg.user > .bubble { background: var(--user-bg); color: var(--user-text); border-top-right-radius: 4px; }
.msg.assistant > .bubble { background: var(--ai-bg); border: 1px solid var(--ai-border); border-top-left-radius: 4px; flex: 1; }
.bubble header { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 11.5px; margin-bottom: 4px; opacity: .9; }
.bubble header .who { font-weight: 700; }
.bubble header time { margin-left: auto; opacity: .75; }
.msg.user a { color: inherit; }
.badge { display: inline-block; font-size: 11px; padding: 0 7px; border-radius: 999px; background: var(--chip-bg); color: var(--muted); }
.msg.user .badge { background: rgba(255,255,255,.2); color: inherit; }
.badge.model { background: rgba(201,100,66,.14); color: var(--accent); }
.badge.effort { background: var(--chip-bg); color: var(--text); }
.badge.err { background: var(--del-bg); color: var(--err); margin-left: 6px; }
.badge.muted { margin-left: 6px; }
.chip { display: inline-block; font-size: 12px; padding: 2px 8px; margin: 4px 4px 0 0; border-radius: 6px; background: var(--chip-bg); color: var(--muted); word-break: break-all; }
.msg.user .chip { background: rgba(255,255,255,.18); color: inherit; }

/* 折り畳み */
.msg-summary { display: none; font-size: 13px; cursor: pointer; }
.msg-summary .sum-label { font-size: 10.5px; font-weight: 700; padding: 0 6px; margin-right: 6px; border-radius: 4px; background: var(--chip-bg); color: var(--muted); }
.msg.user .msg-summary .sum-label { background: rgba(255,255,255,.22); color: inherit; }
.msg-summary .sum-tools { display: block; margin-top: 2px; font-size: 11.5px; opacity: .7; }
.msg.collapsed .msg-summary { display: block; }
.msg.collapsed .msg-body { display: none; }
.fold-btn { margin-top: 6px; border: 0; background: none; color: inherit; opacity: .7; font-size: 12px; cursor: pointer; padding: 0; text-decoration: underline; }
.fold-btn:hover { opacity: 1; }

/* 本文 */
.md > :first-child, .msg-body > p:first-child { margin-top: 0; }
.md > :last-child { margin-bottom: 0; }
.msg-body p { margin: .4em 0; overflow-wrap: anywhere; }
.msg-body h3, .msg-body h4, .msg-body h5, .msg-body h6 { margin: .8em 0 .3em; font-size: 14px; }
.msg-body h3 { font-size: 15px; }
.msg-body ul, .msg-body ol { margin: .3em 0; padding-left: 1.4em; }
.msg-body blockquote { margin: .4em 0; padding: 0 0 0 10px; border-left: 3px solid var(--line); color: var(--muted); }
.msg-body hr { border: 0; border-top: 1px solid var(--line); }
.msg-body code { background: var(--code-bg); padding: 1px 4px; border-radius: 4px; overflow-wrap: anywhere; }
.msg.user .msg-body code { background: rgba(255,255,255,.18); }
pre { margin: .4em 0; padding: 8px 10px; background: var(--code-bg); border-radius: 8px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; max-height: 480px; overflow-y: auto; }
pre code { background: none; padding: 0; }
pre.code { position: relative; }
pre.code .lang { position: absolute; top: 2px; right: 8px; font-size: 10.5px; color: var(--muted); }
.msg.user pre { background: rgba(0,0,0,.18); color: inherit; }
pre.cmd { border-left: 3px solid var(--accent); }
pre.del { background: var(--del-bg); margin-bottom: 2px; }
pre.add { background: var(--add-bg); margin-top: 2px; }
.trunc { font-size: 11.5px; color: var(--muted); }
.table-wrap { overflow-x: auto; margin: .4em 0; }
table { border-collapse: collapse; font-size: 13px; }
th, td { border: 1px solid var(--line); padding: 4px 8px; vertical-align: top; }
th { background: var(--chip-bg); }
img.shot { max-width: 100%; max-height: 420px; border-radius: 8px; margin: 6px 0; display: block; }
.todos { list-style: none; padding-left: 4px !important; }
.todo-completed { color: var(--muted); text-decoration: line-through; }
.todo-in_progress { font-weight: 600; }

/* ツール・思考などの小ブロック */
details > summary { cursor: pointer; list-style: none; }
details > summary::-webkit-details-marker { display: none; }
details > summary::before { content: "▸"; display: inline-block; width: 1em; color: var(--muted); transition: transform .15s; }
details[open] > summary::before { transform: rotate(90deg); }
.tool { margin: 6px 0; border: 1px solid var(--line); border-radius: 8px; background: var(--bg); }
.tool > summary { padding: 4px 8px; font-size: 12.5px; display: flex; align-items: baseline; gap: 4px; min-width: 0; }
.tool-name { font-family: ui-monospace, Menlo, monospace; font-weight: 700; color: var(--accent); flex: none; }
.tool-title { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.tool-body { padding: 0 8px 6px; }
.fold { margin: 6px 0; }
.fold > summary { font-size: 12.5px; color: var(--muted); }
.fold-body { padding: 2px 0 0 14px; }
.fold.thinking > summary { font-style: italic; }
.fold.thinking .fold-body { color: var(--muted); border-left: 2px solid var(--line); padding-left: 10px; margin-left: 4px; }
.fold.subagent > .fold-body { padding-left: 0; }
.subthread { border-left: 3px dashed var(--line); padding-left: 10px; margin-left: 4px; }
.subthread .msg { margin: 8px 0; }
.subthread .bubble { max-width: 100%; }
.msg.user .fold > summary { color: inherit; opacity: .85; }
body.hide-tools .tool, body.hide-thinking .fold.thinking { display: none; }

/* システム行 */
.sys { display: flex; gap: 8px; justify-content: center; align-items: baseline; margin: 10px auto; max-width: 760px;
  font-size: 12px; color: var(--sys-text); text-align: center; }
.sys-time { font-size: 11px; opacity: .7; flex: none; }
.sys-label, .sys-fold > summary { background: var(--chip-bg); padding: 2px 10px; border-radius: 999px; display: inline-block; }
.sys-fold { max-width: 100%; min-width: 0; }
.sys-fold[open] { flex: 1; text-align: left; }
.sys-body { margin-top: 6px; padding: 8px 12px; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; color: var(--text); font-size: 13px; }
.sys.lv-error .sys-label, .sys.lv-error summary { background: var(--del-bg); color: var(--err); }
.sys.lv-warn .sys-label { color: var(--err); }
.sys.lv-compact .sys-label { background: rgba(201,100,66,.14); color: var(--accent); }
body.hide-system .sys { display: none; }

.footer { text-align: center; color: var(--muted); font-size: 11.5px; margin-top: 40px; }
.toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%) translateY(20px); background: var(--text); color: var(--bg);
  padding: 8px 16px; border-radius: 8px; font-size: 13px; opacity: 0; transition: .2s; pointer-events: none; z-index: 50; }
.toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

@media (max-width: 860px) {
  .toc { position: fixed; left: 0; top: 53px; z-index: 15; box-shadow: 2px 0 12px rgba(0,0,0,.15); width: min(300px, 85vw); }
  .toc, body.toc-off .toc { display: none; }
  body.toc-open .toc { display: block; }
  .bubble { max-width: 100%; }
  .msg > .avatar { display: none; }
  .topbar { flex-wrap: wrap; padding: 8px 16px; }
  .topbar h1 { font-size: 13px; flex: 1 1 calc(100% - 60px); }
  .btn-group { flex: 1 1 100%; flex-wrap: nowrap; justify-content: flex-start; overflow-x: auto; padding-bottom: 2px; }
  .toc { top: 0; height: 100vh; z-index: 30; }
  .facts dl { grid-template-columns: 1fr; }
  .btn .lbl { display: none; }
}
@media print {
  .topbar, .toc, .fold-btn { display: none !important; }
  .msg.collapsed .msg-body { display: block; }
  .msg.collapsed .msg-summary { display: none; }
}
</style>
</head>
<body>
<div class="topbar">
  <button class="btn" id="btn-toc" type="button" aria-pressed="true" title="目次の表示を切り替え">☰<span class="lbl"> 目次</span></button>
  <h1>{{TITLE}}</h1>
  <div class="btn-group">
    <button class="btn" id="btn-expand" type="button">すべて展開</button>
    <button class="btn" id="btn-collapse" type="button">長文を折り畳む</button>
    <button class="btn" id="btn-tools" type="button" aria-pressed="true">ツール</button>
    <button class="btn" id="btn-thinking" type="button" aria-pressed="true">思考</button>
    <button class="btn" id="btn-system" type="button" aria-pressed="true">システム</button>
    <button class="btn" id="btn-copy" type="button" title="この HTML をクリップボードにコピー">📋<span class="lbl"> コピー</span></button>
    <button class="btn primary" id="btn-download" type="button" title="この HTML をダウンロード">⬇<span class="lbl"> ダウンロード</span></button>
  </div>
</div>
<div class="layout">
  <nav class="toc" aria-label="目次">
    <h2>目次</h2>
    <ol>{{TOC}}</ol>
  </nav>
  <main>
    <div class="thread">
      <section class="facts"><dl>{{FACTS}}</dl>{{FACTS_NOTE}}</section>
      {{BODY}}
      <div class="footer">claude-code-session-viewer で {{GENERATED}} に生成</div>
    </div>
  </main>
</div>
<div class="toast" id="toast" role="status"></div>
<script>
(function () {
  // 状態を変える前の HTML を保存しておき、コピー・ダウンロードではこれを使う
  var SNAPSHOT = "<!DOCTYPE html>\n" + document.documentElement.outerHTML;
  var FILENAME = {{FILENAME_JS}};
  var body = document.body;

  function store(key, val) { try { localStorage.setItem("ccsv:" + key, val); } catch (e) {} }
  function load(key) { try { return localStorage.getItem("ccsv:" + key); } catch (e) { return null; } }
  function toast(msg) {
    var t = document.getElementById("toast");
    t.textContent = msg; t.classList.add("show");
    clearTimeout(toast._t); toast._t = setTimeout(function () { t.classList.remove("show"); }, 1800);
  }

  // 目次の ON/OFF（広い画面はサイドバー、狭い画面は重ねて表示）
  var narrow = window.matchMedia("(max-width: 860px)");
  var btnToc = document.getElementById("btn-toc");
  function tocVisible() {
    return narrow.matches ? body.classList.contains("toc-open") : !body.classList.contains("toc-off");
  }
  function syncTocButton() { btnToc.setAttribute("aria-pressed", tocVisible() ? "true" : "false"); }
  if (load("toc") === "off") body.classList.add("toc-off");
  syncTocButton();
  btnToc.addEventListener("click", function () {
    if (narrow.matches) {
      body.classList.toggle("toc-open");
    } else {
      var off = body.classList.toggle("toc-off");
      store("toc", off ? "off" : "on");
    }
    syncTocButton();
  });
  if (narrow.addEventListener) narrow.addEventListener("change", syncTocButton);

  // ツール・思考・システム行の表示切り替え
  [["btn-tools", "hide-tools"], ["btn-thinking", "hide-thinking"], ["btn-system", "hide-system"]].forEach(function (pair) {
    var b = document.getElementById(pair[0]);
    b.addEventListener("click", function () {
      var hidden = body.classList.toggle(pair[1]);
      b.setAttribute("aria-pressed", hidden ? "false" : "true");
    });
  });

  // メッセージの折り畳み
  function setCollapsed(msg, collapsed) {
    msg.classList.toggle("collapsed", collapsed);
    var b = msg.querySelector(":scope > .bubble > .fold-btn");
    if (b) { b.textContent = collapsed ? "全文を表示" : "折り畳む"; b.setAttribute("aria-expanded", collapsed ? "false" : "true"); }
  }
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest(".fold-btn");
    if (!b) return;
    var msg = b.closest(".msg");
    var wasCollapsed = msg.classList.contains("collapsed");
    setCollapsed(msg, !wasCollapsed);
    if (!wasCollapsed) msg.scrollIntoView({ block: "nearest" });
  });
  document.addEventListener("click", function (ev) {
    var s = ev.target.closest(".msg-summary");
    if (s) setCollapsed(s.closest(".msg"), false);
  });
  document.getElementById("btn-expand").addEventListener("click", function () {
    document.querySelectorAll(".msg.long").forEach(function (m) { setCollapsed(m, false); });
  });
  document.getElementById("btn-collapse").addEventListener("click", function () {
    document.querySelectorAll(".msg.long").forEach(function (m) { setCollapsed(m, true); });
  });

  // 狭い画面では、目次を選んだら閉じる
  document.querySelectorAll(".toc a").forEach(function (a) {
    a.addEventListener("click", function () {
      if (narrow.matches) { body.classList.remove("toc-open"); syncTocButton(); }
    });
  });

  // 表示中のメッセージを目次で強調
  var links = {};
  document.querySelectorAll(".toc a").forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
  var current = null;
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var a = links[e.target.id];
        if (!a || a === current) return;
        if (current) current.classList.remove("active");
        current = a; a.classList.add("active");
        var toc = document.querySelector(".toc");
        var r = a.getBoundingClientRect(), tr = toc.getBoundingClientRect();
        if (r.top < tr.top || r.bottom > tr.bottom) a.scrollIntoView({ block: "nearest" });
      });
    }, { rootMargin: "-60px 0px -70% 0px" });
    document.querySelectorAll(".thread > .msg[id]").forEach(function (m) { io.observe(m); });
  }

  // ダウンロード
  document.getElementById("btn-download").addEventListener("click", function () {
    var blob = new Blob([SNAPSHOT], { type: "text/html;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = FILENAME;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    toast("ダウンロードしました");
  });

  // クリップボードにコピー（file:// などで Clipboard API が使えない場合は execCommand で代替）
  function legacyCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", "");
    ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) {}
    ta.remove();
    return ok;
  }
  document.getElementById("btn-copy").addEventListener("click", function () {
    var done = function () { toast("HTML をクリップボードにコピーしました"); };
    var fail = function () { toast(legacyCopy(SNAPSHOT) ? "HTML をクリップボードにコピーしました" : "コピーできませんでした"); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(SNAPSHOT).then(done, fail);
    } else {
      fail();
    }
  });
})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Claude Code のセッション履歴を HTML に変換する")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("list", help="セッションの一覧を表示する")
    lp.add_argument("--all", action="store_true", help="全プロジェクトのセッションを表示する")
    lp.add_argument("--project", help="このディレクトリのセッションを表示する（既定: カレントディレクトリ）")
    lp.add_argument("--limit", type=int, default=15)
    rp = sub.add_parser("render", help="セッションを HTML に変換する")
    rp.add_argument("session", help="セッション ID（先頭一致可）または JSONL ファイルのパス")
    rp.add_argument("--out", help="出力先のファイルまたはディレクトリ（既定: %s）" % DEFAULT_OUT_DIR)
    rp.add_argument("--no-subagents", action="store_true", help="サブエージェントのやり取りを含めない")
    args = ap.parse_args()
    if args.cmd == "list":
        cmd_list(args)
    else:
        cmd_render(args)


if __name__ == "__main__":
    main()
