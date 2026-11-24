"""Tests for the claude-code-session-viewer script and its ccsv package.

Run from the repository root:
    python3 -m unittest discover -s tests
"""

import base64
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "claude-code-session-viewer" / "scripts"
ENTRY = SCRIPTS / "render_session.py"
ASSETS = SCRIPTS / "ccsv" / "assets"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "00000000-0000-4000-8000-000000000001.jsonl"

sys.path.insert(0, str(SCRIPTS))
import render_session  # noqa: E402
from ccsv import i18n, render, transcript  # noqa: E402
from ccsv.messages import MESSAGES  # noqa: E402

JAPANESE_RE = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")


def placeholders(template):
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def base_keys(table):
    return {k for k in table if not k.endswith("_one")}


def render_fixture(lang):
    i18n.set_lang(lang)
    builder = transcript.Builder(FIXTURE)
    items = builder.build()
    page, _ = render.render_page(builder, items)
    return builder, page


class ResetLangMixin:
    def tearDown(self):
        i18n.set_lang(i18n.DEFAULT_LANG)


class MessagesTest(ResetLangMixin, unittest.TestCase):
    def test_every_language_has_the_same_keys(self):
        reference = base_keys(MESSAGES[i18n.DEFAULT_LANG])
        for lang, table in MESSAGES.items():
            with self.subTest(lang=lang):
                self.assertEqual(base_keys(table), reference)

    def test_plural_variants_have_a_base_key(self):
        for lang, table in MESSAGES.items():
            for key in table:
                if key.endswith("_one"):
                    with self.subTest(lang=lang, key=key):
                        self.assertIn(key[: -len("_one")], table)

    def test_placeholders_match_across_languages(self):
        reference = MESSAGES[i18n.DEFAULT_LANG]
        for lang, table in MESSAGES.items():
            for key, template in table.items():
                with self.subTest(lang=lang, key=key):
                    if key.endswith("_one"):
                        # The singular form may drop {n}, but must not need anything extra.
                        self.assertLessEqual(placeholders(template), placeholders(table[key[: -len("_one")]]))
                    else:
                        self.assertEqual(placeholders(template), placeholders(reference[key]))

    def test_no_placeholder_named_key(self):
        # t(key, **kw) takes the message key as its first argument, so "{key}" in a message cannot be filled.
        for lang, table in MESSAGES.items():
            for key, template in table.items():
                with self.subTest(lang=lang, key=key):
                    self.assertNotIn("key", placeholders(template))

    def test_plural_selection(self):
        i18n.set_lang("en")
        self.assertEqual(i18n.t("result_lines", n=1), "Result (1 line)")
        self.assertEqual(i18n.t("result_lines", n=2), "Result (2 lines)")
        i18n.set_lang("ja")
        self.assertEqual(i18n.t("result_lines", n=1), "結果（1 行）")


class AssetsTest(unittest.TestCase):
    def test_template_keys_exist(self):
        page = (ASSETS / "page.html").read_text(encoding="utf-8")
        used = set(re.findall(r"\{\{t:([a-z_]+)\}\}", page)) | set(render.JS_MESSAGE_KEYS)
        self.assertTrue(used)
        for lang, table in MESSAGES.items():
            with self.subTest(lang=lang):
                self.assertEqual(used - set(table), set())

    def test_app_js_only_uses_messages_it_is_given(self):
        app = (ASSETS / "app.js").read_text(encoding="utf-8")
        used = set(re.findall(r"\bMSG\.([a-z_]+)", app))
        self.assertTrue(used)
        self.assertEqual(used - set(render.JS_MESSAGE_KEYS), set())

    def test_toc_sync_does_not_scroll_the_page(self):
        # scrollIntoView() in the TOC highlight code interrupted the user's scrolling (scrolling up from the
        # bottom stuttered). The highlight code must scroll only the TOC box.
        app = (ASSETS / "app.js").read_text(encoding="utf-8")
        start = app.index("// Highlight the message currently in view")
        end = app.index("// Download", start)
        self.assertNotIn(".scrollIntoView(", app[start:end])

    def test_style_and_script_have_no_placeholders(self):
        # Placeholders are only allowed in page.html; anywhere else they would be substituted by mistake.
        for name in ("style.css", "app.js"):
            with self.subTest(name=name):
                self.assertNotIn("{{", (ASSETS / name).read_text(encoding="utf-8"))


class RenderTest(ResetLangMixin, unittest.TestCase):
    def test_english_output_has_no_japanese(self):
        _, page = render_fixture("en")
        found = sorted(set(JAPANESE_RE.findall(page)))
        self.assertEqual(found, [], "Japanese characters left in the English page")
        self.assertIn('<html lang="en">', page)
        for expected in (
            "Result (2 lines)",
            "Error details (1 line)",
            "Written content (1 line)",
            "Conversation compacted (manual, 12,345 tokens before)",
            "Subagent conversation (Explore, 2 messages",
            "Total tokens (including subagents)",
            "Sent while Claude was working",
            "Loaded skill: example-skill",
            "Background task notification (completed): Background job finished",
            "Interrupted by the user",
            "Command: /compact",
            "Entered plan mode",
            "Exited plan mode",
            "Linked to a pull request",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)

    def test_japanese_output(self):
        _, page = render_fixture("ja")
        self.assertIn('<html lang="ja">', page)
        for expected in (
            "結果（2 行）",
            "会話を圧縮しました（手動・圧縮前 12,345 トークン）",
            "サブエージェントのやり取り（Explore・2 件",
            "トークン合計（サブエージェントを含む）",
            "目次",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)

    def test_page_is_complete(self):
        _, page = render_fixture("en")
        self.assertNotIn("{{", page)  # every placeholder was filled
        self.assertIn("--bg: #f4f5f7", page)  # style.css was inlined
        self.assertIn('getElementById("ccsv-data")', page)  # app.js was inlined
        self.assertIn('"filename": "Sample_session_00000000_en.html"', page)

    def test_internal_records_are_hidden(self):
        _, page = render_fixture("en")
        self.assertNotIn("internal note that must not be shown", page)

    def test_token_totals(self):
        builder, _ = render_fixture("en")
        # Six main responses (msg_1 is split over two records but counted once) plus one subagent response.
        self.assertEqual(builder.usage, {"input": 60, "cache_create": 600, "cache_read": 6000, "output": 300})
        self.assertEqual(builder.sub_usage, {"input": 5, "cache_create": 0, "cache_read": 200, "output": 20})
        self.assertEqual(builder.total_usage()["output"], 320)
        self.assertEqual(set(builder.usage_by_model), {"claude-opus-5-5", "claude-haiku-5-5"})


class LanguageDetectionTest(unittest.TestCase):
    def detect(self, env, platform="linux"):
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(i18n.sys, "platform", platform):
            return i18n.detect_lang()

    def test_locale_variables(self):
        self.assertEqual(self.detect({"LANG": "ja_JP.UTF-8"}), "ja")
        self.assertEqual(self.detect({"LANG": "en_US.UTF-8"}), "en")
        self.assertEqual(self.detect({"LANG": "fr_FR.UTF-8"}), "en")
        self.assertEqual(self.detect({"LC_ALL": "ja_JP.UTF-8", "LANG": "en_US.UTF-8"}), "ja")

    def test_c_locale_is_not_a_language(self):
        self.assertEqual(self.detect({"LANG": "C.UTF-8"}), "en")
        self.assertEqual(self.detect({"LANG": "POSIX"}), "en")
        self.assertEqual(self.detect({}), "en")

    def test_macos_system_language_is_used_when_locale_is_c(self):
        result = mock.Mock(stdout='(\n    "ja-JP"\n)\n')
        with mock.patch.object(i18n.subprocess, "run", return_value=result):
            self.assertEqual(self.detect({"LANG": "C.UTF-8"}, platform="darwin"), "ja")


class CommandLineTest(ResetLangMixin, unittest.TestCase):
    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            render_session.main(list(argv))
        return out.getvalue()

    def test_lang_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            en = self.run_main("render", str(FIXTURE), "--lang", "en", "--out", tmp)
            self.assertIn("Wrote:", en)
            ja = self.run_main("render", str(FIXTURE), "--lang", "ja", "--out", tmp)
            self.assertIn("出力しました:", ja)
            # The language is part of the file name, so the two pages do not overwrite each other.
            self.assertEqual(sorted(p.name for p in Path(tmp).glob("*.html")),
                             ["Sample_session_00000000_en.html", "Sample_session_00000000_ja.html"])

    def test_list_is_scoped_to_the_current_sessions_project(self):
        with tempfile.TemporaryDirectory() as projects, tempfile.TemporaryDirectory() as elsewhere:
            for project, session in (("-work-project-a", "aaaaaaaa-0000"), ("-work-project-b", "bbbbbbbb-0000")):
                (Path(projects) / project).mkdir()
                (Path(projects) / project / (session + ".jsonl")).write_text(
                    '{"type":"ai-title","aiTitle":"title %s"}\n' % session, encoding="utf-8")
            cwd = os.getcwd()
            try:
                os.chdir(elsewhere)  # the shell is not in either project
                with mock.patch.object(transcript, "PROJECTS_DIR", Path(projects)):
                    scoped = self.run_main("list", "--current-session", "aaaaaaaa", "--lang", "en")
                    unscoped = self.run_main("list", "--lang", "en")
            finally:
                os.chdir(cwd)
            self.assertIn("aaaaaaaa-0000", scoped)
            self.assertNotIn("bbbbbbbb-0000", scoped)
            self.assertNotIn("No sessions found", scoped)
            # Without --current-session the current directory decides, which matches no project here.
            self.assertIn("No sessions found", unscoped)
            self.assertIn("bbbbbbbb-0000", unscoped)

    def test_lang_option_before_the_subcommand(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_main("--lang", "en", "render", str(FIXTURE), "--out", tmp)
            self.assertIn("Wrote:", out)

    def test_help_is_localized(self):
        for lang, expected in (("en", "convert a session into HTML"), ("ja", "セッションを HTML に変換する")):
            with self.subTest(lang=lang), self.assertRaises(SystemExit):
                out = io.StringIO()
                try:
                    with contextlib.redirect_stdout(out):
                        render_session.main(["--lang", lang, "--help"])
                finally:
                    self.assertIn(expected, out.getvalue())

    def test_runs_in_isolated_mode(self):
        # -I leaves the script's directory out of sys.path; the entry point must still find ccsv.
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, "-I", "-B", str(ENTRY), "render", str(FIXTURE), "--lang", "en", "--out", tmp],
                capture_output=True, text=True, cwd=tmp, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Wrote:", proc.stdout)


def write_jsonl(directory, name, records):
    path = Path(directory) / name
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write((rec if isinstance(rec, str) else json.dumps(rec)) + "\n")
    return path


def user_rec(content, **extra):
    rec = {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "message": {"role": "user", "content": content}}
    rec.update(extra)
    return rec


def assistant_rec(blocks, msg_id="m1"):
    return {"type": "assistant", "timestamp": "2026-01-01T00:00:01Z",
            "message": {"id": msg_id, "model": "claude-opus-5-5", "role": "assistant", "content": blocks}}


def render_records(records, lang="en", **filters):
    with tempfile.TemporaryDirectory() as tmp:
        path = write_jsonl(tmp, "abcd0000-0000.jsonl", records)
        i18n.set_lang(lang)
        builder = transcript.Builder(path)
        items = render.filter_items(builder.build(), **filters)
        return render.render_page(builder, items)


class SecurityTest(ResetLangMixin, unittest.TestCase):
    def test_file_name_keeps_only_safe_characters(self):
        title = "$(touch${IFS}PWNED)`id`;&'x'../../..\\..\\etc <b>"
        _, filename = render_records([{"type": "custom-title", "customTitle": title}, user_rec("hi")])
        self.assertRegex(filename, r"^[\w.-]+$")
        self.assertNotIn("/", filename)
        self.assertTrue(filename.endswith("_abcd0000_en.html"))

    def test_code_inside_link_text(self):
        from ccsv.markdown import md_inline
        cases = {
            "[`c`](http://z/)": '<a href="http://z/" target="_blank" rel="noopener noreferrer"><code>c</code></a>',
            "see [the `slugify` docs](https://example.com/d)":
                'see <a href="https://example.com/d" target="_blank" rel="noopener noreferrer">'
                "the <code>slugify</code> docs</a>",
        }
        for src, expected in cases.items():
            with self.subTest(src=src):
                self.assertEqual(md_inline(src), expected)
        # Code inside the URL is not turned into a broken link, and no fragment marker is ever left behind.
        for src in ("[x](https://e.com/`y`)", "https://example.com/a`b`", "[`a` `b`](https://e.com) `c`"):
            with self.subTest(src=src):
                out = md_inline(src)
                self.assertNotIn("\ue000", out)
                self.assertNotIn("\ue001", out)
                self.assertNotRegex(out, r'href="[^"]*<code>')

    def test_only_http_links_are_links(self):
        page, _ = render_records([
            {"type": "pr-link", "timestamp": "2026-01-01T00:00:00Z", "prUrl": "javascript:alert(1)//https://x"},
            {"type": "pr-link", "timestamp": "2026-01-01T00:00:01Z", "prUrl": "https://github.com/example/example/pull/1"},
            assistant_rec([{"type": "text", "text": "[a](javascript:alert(1)) [b](https://example.com/b)"}]),
        ])
        hrefs = re.findall(r'href="([^"]*)"', page)
        self.assertFalse([h for h in hrefs if not (h.startswith("https://") or h.startswith("#"))], hrefs)
        self.assertIn("https://github.com/example/example/pull/1", hrefs)
        self.assertIn("javascript:alert(1)//https://x", page)  # still visible, as text
        self.assertNotIn('rel="noopener"', page)  # every link also has noreferrer

    def test_only_safe_embedded_images(self):
        page, _ = render_records([user_rec([
            {"type": "text", "text": "images"},
            {"type": "image", "source": {"type": "url", "url": "https://attacker.example/beacon.png"}},
            {"type": "image", "source": {"type": "base64", "media_type": "image/svg+xml", "data": "PHN2Zz4="}},
            {"type": "image", "source": {"type": "base64", "media_type": 'image/png" onerror="x', "data": "AAAA"}},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="}},
        ])])
        srcs = re.findall(r'<img[^>]* src="([^"]*)"', page)
        self.assertEqual(srcs, ["data:image/png;base64,iVBORw0KGgo="])
        self.assertNotIn("attacker.example", page)

    def test_content_security_policy_allows_only_app_js(self):
        _, page = render_fixture("en")
        csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]*)"', page).group(1)
        self.assertIn("default-src 'none'", csp)
        self.assertIn("img-src data:", csp)
        inline = re.findall(r"<script>(.*?)</script>", page, re.S)
        self.assertEqual(len(inline), 1)
        digest = base64.b64encode(hashlib.sha256(inline[0].encode()).digest()).decode()
        self.assertIn("script-src 'sha256-%s'" % digest, csp)
        self.assertIn('<meta name="referrer" content="no-referrer">', page)

    def test_saved_copies_and_windows_line_endings_are_recognised(self):
        _, page = render_fixture("en")
        downloaded = page.replace('<html lang="en">\n<head>', '<html lang="en"><head>', 1)  # what Download saves
        self.assertNotEqual(downloaded, page)
        for name, variant in (("downloaded copy", downloaded), ("CRLF", page.replace("\n", "\r\n"))):
            with self.subTest(name):
                self.assertTrue(render.is_generated_page(variant))

    def test_page_check_runs_in_linear_time(self):
        _, page = render_fixture("en")
        start = time.time()
        self.assertFalse(render.is_generated_page(page + "<script " * 200000))
        self.assertLess(time.time() - start, 2)

    def test_generated_pages_are_recognised_in_every_language(self):
        for lang in MESSAGES:
            with self.subTest(lang=lang):
                _, page = render_fixture(lang)
                self.assertTrue(render.is_generated_page(page))
                self.assertFalse(render.is_generated_page(page.replace("</body>", "<script></script></body>")))

    def test_privacy_notice_on_page_and_in_output(self):
        _, page = render_fixture("en")
        self.assertIn("Copy and Download include everything in this page", page)
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                render_session.main(["render", str(FIXTURE), "--lang", "en", "--out", tmp])
        self.assertIn("do not publish it", out.getvalue())

    def test_documented_items_stay_with_no_tools_and_no_thinking(self):
        # README ("Privacy and sharing") lists what these options do NOT remove; every item is checked here,
        # so the list cannot silently become wrong. One record per documented item, each with a marker.
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        records = [
            {"type": "custom-title", "customTitle": "MARK_TITLE"},
            user_rec([{"type": "text", "text": "<ide_selection>The user selected the lines 1 to 2 from /tmp/MARK_SEL.py:\nx</ide_selection>"
                                               "MARK_USER_MESSAGE"},
                      {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png}},
                      {"type": "document", "title": "MARK_DOCUMENT_TITLE",
                       "source": {"type": "base64", "media_type": "application/pdf", "data": "MARK_DOCUMENT_DATA"}}],
                     cwd="/tmp/MARK_CWD", gitBranch="MARK_BRANCH"),
            assistant_rec([{"type": "thinking", "thinking": "MARK_THINKING_GONE"},
                           {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "MARK_TOOL_GONE"}},
                           {"type": "text", "text": "MARK_CLAUDE_REPLY"}]),
            user_rec("<command-name>/MARK_SLASH</command-name><command-args>MARK_ARGS</command-args>"),
            user_rec("<local-command-stdout>MARK_COMMAND_OUTPUT</local-command-stdout>"),
            user_rec("<task-notification><task-id>x</task-id><status>completed</status>"
                     "<result>MARK_TASK_RESULT</result></task-notification>"),
            {"type": "attachment", "timestamp": "2026-01-01T00:00:02Z", "attachment": {
                "type": "hook_success", "hookName": "PreToolUse:Bash", "exitCode": 0, "stdout": "", "stderr": "MARK_HOOK"}},
            user_rec([{"type": "text", "text": "Base directory for this skill: /tmp/s\n\nMARK_SKILL_BODY"}], isMeta=True),
            {"type": "attachment", "timestamp": "2026-01-01T00:00:03Z",
             "attachment": {"type": "edited_text_file", "filename": "/tmp/MARK_EDITED.py"}},
            {"type": "attachment", "timestamp": "2026-01-01T00:00:03Z",
             "attachment": {"type": "file", "filename": "/tmp/MARK_ATTACHED.md"}},
            {"type": "attachment", "timestamp": "2026-01-01T00:00:04Z",
             "attachment": {"type": "plan_mode_exit", "planFilePath": "/tmp/MARK_PLAN.md"}},
            {"type": "assistant", "timestamp": "2026-01-01T00:00:05Z", "isApiErrorMessage": True,
             "message": {"id": "e", "model": "<synthetic>", "content": [{"type": "text", "text": "MARK_API_ERROR"}]}},
            user_rec("Summary: MARK_COMPACT_SUMMARY", isCompactSummary=True),
            {"type": "pr-link", "timestamp": "2026-01-01T00:00:06Z", "prUrl": "https://github.com/example/MARK_PR/pull/1"},
        ]
        page, _ = render_records(records, include_tools=False, include_thinking=False)
        kept = ["MARK_TITLE", "/tmp/MARK_CWD", "MARK_BRANCH", "abcd0000-0000",   # session details
                "MARK_USER_MESSAGE", 'src="data:image/png;base64,', "MARK_CLAUDE_REPLY",  # the conversation
                "MARK_COMMAND_OUTPUT", "MARK_TASK_RESULT", "MARK_HOOK", "MARK_SKILL_BODY", "MARK_SEL.py",
                "MARK_COMPACT_SUMMARY", "MARK_SLASH", "MARK_ARGS", "MARK_EDITED.py", "MARK_ATTACHED.md",
                "MARK_PLAN.md", "MARK_API_ERROR", "MARK_PR"]
        for marker in kept:
            with self.subTest(kept=marker):
                self.assertIn(marker, page)
        self.assertIn("MARK_DOCUMENT_TITLE", page)  # the title of an attached document (its data is never shown)
        for marker in ("MARK_THINKING_GONE", "MARK_TOOL_GONE", "MARK_DOCUMENT_DATA"):
            with self.subTest(removed=marker):
                self.assertNotIn(marker, page)

    def test_tools_and_thinking_can_be_left_out(self):
        _, full = render_fixture("en")
        builder = transcript.Builder(FIXTURE)
        page, _ = render.render_page(builder, render.filter_items(builder.build(), include_tools=False,
                                                                  include_thinking=False))
        self.assertIn('class="tool"', full)
        self.assertIn("Let me look at the directory first.", full)
        self.assertNotIn('class="tool"', page)
        self.assertNotIn("Let me look at the directory first.", page)  # thinking
        self.assertNotIn("Find all Python files.", page)  # subagent conversation lives inside a tool call
        self.assertIn("Done. The fix is in", page)  # Claude's text stays

    def test_no_thinking_alone_also_removes_subagent_thinking(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = write_jsonl(tmp, "abcd0000-0000.jsonl", [
                user_rec("start"),
                assistant_rec([{"type": "thinking", "thinking": "MAIN_THINKING_MARK"},
                               {"type": "tool_use", "id": "toolu_sub", "name": "Agent",
                                "input": {"description": "d", "prompt": "p"}}]),
            ])
            sub_dir = Path(tmp) / "abcd0000-0000" / "subagents"
            sub_dir.mkdir(parents=True)
            write_jsonl(sub_dir, "agent-x.jsonl", [
                user_rec("p"),
                assistant_rec([{"type": "thinking", "thinking": "SUB_THINKING_MARK"},
                               {"type": "text", "text": "SUB_TEXT_MARK"}], msg_id="s1"),
            ])
            (sub_dir / "agent-x.meta.json").write_text('{"toolUseId": "toolu_sub", "agentType": "Explore"}',
                                                       encoding="utf-8")
            i18n.set_lang("en")
            builder = transcript.Builder(main)
            items = builder.build()
            full, _ = render.render_page(builder, items)
            page, _ = render.render_page(builder, render.filter_items(items, include_thinking=False))
        self.assertIn("SUB_THINKING_MARK", full)
        self.assertNotIn("MAIN_THINKING_MARK", page)
        self.assertNotIn("SUB_THINKING_MARK", page)
        self.assertIn("SUB_TEXT_MARK", page)  # the subagent conversation itself stays


class RobustnessTest(ResetLangMixin, unittest.TestCase):
    """Malformed or hostile transcripts must neither crash rendering nor make it slow."""

    CASES = {
        "table separator with many spaces": [assistant_rec([{"type": "text", "text": "a|b\n--" + " " * 30000 + "x"}])],
        "many unclosed tags": [user_rec("<system-reminder>" * 20000 + "hello")],
        "many unclosed task tags": [user_rec("<task-notification>" + "<task-id>" * 20000)],
        "many brackets": [assistant_rec([{"type": "text", "text": "[" * 50000}])],
        "many bold markers": [assistant_rec([{"type": "text", "text": "**x " * 30000}])],
        "deeply nested quote": [assistant_rec([{"type": "text", "text": ">" * 3000 + " x"}])],
        "forged fragment marker": [assistant_rec([{"type": "text", "text": "\x001\x00 0 `code`"}])],
        "numeric timestamp": [{"type": "user", "timestamp": 123, "message": {"role": "user", "content": "hi"}}],
        "array record": ["[]"],
        "deeply nested JSON": ["[" * 100000 + "]" * 100000],
        "wrong tool field types": [assistant_rec([{"type": "tool_use", "id": ["x"], "name": ["x"], "input": [1]}]),
                                   user_rec([{"type": "tool_result", "tool_use_id": ["x"], "content": "r"}])],
        "wrong todo status type": [assistant_rec([{"type": "tool_use", "id": "t", "name": "TodoWrite",
                                                   "input": {"todos": [{"status": ["x"], "content": "a"}]}}])],
        "titles that are not strings": [{"type": "custom-title", "customTitle": {"a": 1}},
                                        {"type": "ai-title", "aiTitle": 12345},
                                        user_rec("hi", cwd=["x"], gitBranch=7)],
        "repeated phrases in IDE tags": [user_rec("<ide_opened_file>" + "opened the file " * 20000
                                                  + "</ide_opened_file><ide_selection>"
                                                  + "selected the lines 1 to 2 from " * 12000
                                                  + "</ide_selection>question")],
    }

    def test_hostile_inputs(self):
        for name, records in self.CASES.items():
            with self.subTest(name):
                start = time.time()
                page, _ = render_records(list(records) + [user_rec("still rendered")])
                self.assertLess(time.time() - start, 3, "rendering took too long")
                self.assertIn("still rendered", page)

    def test_an_item_that_fails_becomes_a_warning(self):
        i18n.set_lang("en")
        broken = {"kind": "assistant", "ts": None, "parts": [{"type": "unknown"}], "models": None,
                  "efforts": [], "usage": None, "sub_usage": None}
        html_out = render.render_item(broken, 0)
        self.assertIn("could not be displayed", html_out)

    def test_short_session_ids_are_rejected(self):
        for arg in ("", "abc", "../x"):
            with self.subTest(arg=arg), self.assertRaises(transcript.SessionLookupError):
                transcript.resolve_session(arg)


class OutputFileTest(ResetLangMixin, unittest.TestCase):
    def run_render(self, out):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render_session.main(["render", str(FIXTURE), "--lang", "en", "--out", out])
        return buf.getvalue()

    def test_only_generated_pages_are_overwritten_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "index.html"
            target.write_text("<h1>my project</h1>", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.run_render(str(target))
            self.assertEqual(target.read_text(encoding="utf-8"), "<h1>my project</h1>")
            # With --force it is replaced.
            with contextlib.redirect_stdout(io.StringIO()):
                render_session.main(["render", str(FIXTURE), "--lang", "en", "--out", str(target), "--force"])
            self.assertIn('id="ccsv-data"', target.read_text(encoding="utf-8"))
            # A page generated by the tool is replaced without --force (exporting the same session again).
            self.run_render(str(target))
            # So is a page from a version before the data block existed (recognised by its footer).
            legacy = Path(tmp) / "legacy.html"
            legacy.write_text('<div class="footer">claude-code-session-viewer で 2026-11-20 03:00 に生成</div>',
                              encoding="utf-8")
            self.run_render(str(legacy))
            self.assertIn('id="ccsv-data"', legacy.read_text(encoding="utf-8"))

    def test_never_writes_inside_the_skill(self):
        # A stand-in skill directory, so that a bug could never touch the real template.
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "skill"
            (skill / "scripts" / "ccsv" / "assets").mkdir(parents=True)
            template = skill / "scripts" / "ccsv" / "assets" / "page.html"
            template.write_text('<script id="ccsv-data" type="application/json">{{DATA_JSON}}</script>',
                                encoding="utf-8")
            with mock.patch.object(render_session, "SKILL_DIR", skill.resolve()):
                for args in ([], ["--force"]):
                    with self.subTest(args=args), self.assertRaises(SystemExit):
                        render_session.main(["render", str(FIXTURE), "--lang", "en", "--out", str(template)] + args)
            self.assertIn("{{DATA_JSON}}", template.read_text(encoding="utf-8"))

    def test_skill_directory_is_compared_by_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "skill"
            (skill / "assets").mkdir(parents=True)
            template = skill / "assets" / "page.html"
            template.write_text('<script id="ccsv-data" type="application/json">{{DATA_JSON}}</script>',
                                encoding="utf-8")
            # The template is never taken for a generated page, even outside the skill (defence in depth).
            self.assertFalse(render_session.looks_generated(template))
            other_case = Path(tmp) / "SKILL" / "assets" / "page.html"
            with mock.patch.object(render_session, "SKILL_DIR", skill.resolve()):
                self.assertTrue(render_session.inside_skill(skill.resolve() / "assets" / "new"))
                self.assertFalse(render_session.inside_skill(Path(tmp).resolve()))
                if other_case.exists():  # a case-insensitive file system, as on macOS by default
                    with self.assertRaises(SystemExit):
                        self.run_render(str(other_case))
            self.assertIn("{{DATA_JSON}}", template.read_text(encoding="utf-8"))

    def test_session_mentioning_the_template_placeholder_can_be_exported_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "00000000-0000-4000-8000-0000000000ab.jsonl"
            src.write_text(json.dumps(user_rec("please fix the {{DATA_JSON}} placeholder in page.html")) + "\n",
                           encoding="utf-8")
            out = Path(tmp) / "out.html"
            for _ in range(2):
                with contextlib.redirect_stdout(io.StringIO()):
                    render_session.main(["render", str(src), "--lang", "en", "--out", str(out)])
            self.assertIn("{{DATA_JSON}}", out.read_text(encoding="utf-8"))

    def test_interrupted_write_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(render_session.os, "replace", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    self.run_render(tmp + "/out/")
            self.assertEqual(list((Path(tmp) / "out").iterdir()), [])

    def test_lone_surrogate_does_not_stop_the_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "00000000-0000-4000-8000-0000000000aa.jsonl"
            src.write_text(json.dumps({"type": "user", "uuid": "u1", "timestamp": "2026-11-20T03:00:00Z",
                                       "message": {"role": "user", "content": "bad \ud800 text"}}) + "\n",
                           encoding="utf-8")
            out = Path(tmp) / "out.html"
            with contextlib.redirect_stdout(io.StringIO()):
                render_session.main(["render", str(src), "--lang", "en", "--out", str(out)])
            self.assertIn("bad ? text", out.read_text(encoding="utf-8"))
            self.assertEqual([p.name for p in Path(tmp).iterdir() if p.name.startswith(".ccsv-")], [])

    def test_refusal_does_not_suggest_force_to_claude(self):
        for lang in ("en", "ja"):
            i18n.set_lang(lang)
            message = i18n.t("err_out_exists", path="x.html")
            self.assertNotIn("pass --force", message)
            self.assertNotIn("--force を付けてください", message)

    def test_damaged_template_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "assets"
            shutil.copytree(render.ASSETS_DIR, assets)
            page = assets / "page.html"
            page.write_text(page.read_text(encoding="utf-8").replace("{{BODY}}", ""), encoding="utf-8")
            with mock.patch.object(render, "ASSETS_DIR", assets), self.assertRaises(SystemExit) as cm:
                render_session.main(["render", str(FIXTURE), "--lang", "en", "--out", tmp + "/out/"])
            self.assertIn("{{BODY}}", str(cm.exception.code))
            self.assertFalse((Path(tmp) / "out").exists() and any((Path(tmp) / "out").iterdir()))

    def test_failed_write_keeps_the_old_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_render(tmp + "/out/")
            page = next((Path(tmp) / "out").glob("*.html"))
            before = page.read_bytes()
            with mock.patch.object(render_session.os, "replace", side_effect=OSError(28, "No space left on device")):
                with self.assertRaises(SystemExit):
                    self.run_render(str(page))
            self.assertEqual(page.read_bytes(), before)
            self.assertEqual([p.name for p in (Path(tmp) / "out").iterdir()], [page.name])  # no temp file left

    def test_empty_file_and_non_regular_destinations(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.html"
            empty.touch()
            self.run_render(str(empty))  # what an interrupted older write could leave behind: replaced
            self.assertIn('id="ccsv-data"', empty.read_text(encoding="utf-8"))
            if hasattr(os, "mkfifo"):
                fifo = Path(tmp) / "fifo.html"
                os.mkfifo(fifo)
                with self.assertRaises(SystemExit):
                    self.run_render(str(fifo))

    def test_skill_never_passes_force(self):
        skill_md = (ROOT / "skills" / "claude-code-session-viewer" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotRegex(skill_md, r"render_session\.py\"[^\n`]*--force")
        self.assertIn("Never pass `--force`", skill_md)

    def test_out_rules_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A missing directory, with or without a trailing slash, is created.
            self.run_render(tmp + "/newdir/")
            self.run_render(tmp + "/report")
            for d in ("newdir", "report"):
                files = list((Path(tmp) / d).glob("*.html"))
                self.assertEqual(len(files), 1, d)
                self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
            # An existing file that is not .html is never overwritten.
            keep = Path(tmp) / "keep.txt"
            keep.write_text("keep", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.run_render(str(keep))
            self.assertEqual(keep.read_text(encoding="utf-8"), "keep")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "needs O_NOFOLLOW")
    def test_symbolic_link_at_destination_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = Path(tmp) / "victim.txt"
            victim.write_text("victim", encoding="utf-8")
            (Path(tmp) / "link.html").symlink_to(victim)
            with self.assertRaises(SystemExit):
                self.run_render(str(Path(tmp) / "link.html"))
            self.assertEqual(victim.read_text(encoding="utf-8"), "victim")

    def test_open_accepts_only_generated_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "other.html"
            other.write_text("<p>not ours</p>", encoding="utf-8")
            secret = Path(tmp) / "secret.txt"
            secret.write_text("secret", encoding="utf-8")
            disguised = Path(tmp) / "link.html"
            disguised.symlink_to(secret)
            with mock.patch.object(render_session.webbrowser, "open") as opened:
                for path in (Path(tmp) / "missing.html", Path(tmp), other, disguised):
                    with self.subTest(path=path), self.assertRaises(SystemExit):
                        render_session.main(["open", str(path), "--lang", "en"])
                opened.assert_not_called()
            # Pages that only imitate a generated page are refused too.
            self.run_render(tmp + "/gen/")
            genuine = next((Path(tmp) / "gen").glob("*.html")).read_text(encoding="utf-8")
            marker = '<script id="ccsv-data" type="application/json">{}</script>'
            forged = {
                "marker only": "<html><body>%s<script>fetch('x')</script></body></html>" % marker,
                "extra script": genuine.replace("</body>", "<script>alert(1)</script></body>"),
                "extra upper-case script": genuine.replace("</body>", "<SCRIPT SRC=x.js></SCRIPT></body>"),
                "changed CSP": re.sub(r"sha256-[A-Za-z0-9+/=]+", "sha256-AAAA", genuine, count=1),
                "script before the head": "<script>alert(1)</script>" + genuine,
                "meta refresh in the body": genuine.replace(
                    "</body>", '<meta http-equiv="refresh" content="0;url=https://attacker.example/">\n</body>'),
                "meta refresh in the head": genuine.replace(
                    "<title>", '<meta http-equiv="refresh" content="0;url=file:///tmp/evil.html"><title>', 1),
                "upper-case META": genuine.replace("</body>", "<META HTTP-EQUIV=refresh CONTENT=0;url=x></body>"),
                "link": genuine.replace("</body>", '<link rel="dns-prefetch" href="//leak.attacker.example"></body>'),
                "base": genuine.replace("<title>", '<base href="https://attacker.example/"><title>', 1),
                "iframe srcdoc": genuine.replace(
                    "</body>", '<iframe srcdoc="&lt;link rel=dns-prefetch href=//leak.attacker.example&gt;"></iframe></body>'),
                "object": genuine.replace("</body>", '<object data="https://attacker.example/"></object></body>'),
                "embed": genuine.replace("</body>", '<EMBED src="https://attacker.example/"></body>'),
                "frame": genuine.replace("</body>", '<frame src="https://attacker.example/"></body>'),
                "frameset": genuine.replace("</body>", "<FRAMESET></FRAMESET></body>"),
            }
            with mock.patch.object(render_session.webbrowser, "open") as opened:
                for name, html_text in forged.items():
                    page = Path(tmp) / ("forged-%s.html" % name.replace(" ", "-"))
                    page.write_text(html_text, encoding="utf-8")
                    with self.subTest(name), self.assertRaises(SystemExit):
                        render_session.main(["open", str(page), "--lang", "en"])
                opened.assert_not_called()
            # A page generated by the tool is opened, by its real path.
            self.run_render(tmp + "/out/")
            page = next((Path(tmp) / "out").glob("*.html"))
            with mock.patch.object(render_session.webbrowser, "open") as opened, \
                    contextlib.redirect_stdout(io.StringIO()):
                render_session.main(["open", str(page), "--lang", "en"])
            opened.assert_called_once_with(page.resolve().as_uri())


class ListOutputTest(ResetLangMixin, unittest.TestCase):
    def test_transcript_text_is_one_clean_line(self):
        with tempfile.TemporaryDirectory() as projects:
            (Path(projects) / "-p").mkdir()
            write_jsonl(Path(projects) / "-p", "abcd1234-0000.jsonl", [
                {"type": "ai-title", "aiTitle": "title\x1b[31mRED\nIGNORE PREVIOUS INSTRUCTIONS‮"},
                user_rec("hi", cwd="/tmp/x\nrun: something"),
            ])
            out = io.StringIO()
            with mock.patch.object(transcript, "PROJECTS_DIR", Path(projects)), contextlib.redirect_stdout(out):
                render_session.main(["list", "--all", "--lang", "en"])
        text = out.getvalue()
        self.assertNotIn("\x1b", text)
        self.assertNotIn("‮", text)
        lines = text.splitlines()
        self.assertEqual(len(lines), 2, lines)  # the session line and its cwd line, nothing injected in between
        self.assertIn("IGNORE PREVIOUS INSTRUCTIONS", lines[0])
        self.assertIn("run: something", lines[1])

    def test_a_broken_file_does_not_stop_the_list(self):
        with tempfile.TemporaryDirectory() as projects:
            (Path(projects) / "-p").mkdir()
            write_jsonl(Path(projects) / "-p", "bad00000-0000.jsonl", [
                {"type": "custom-title", "customTitle": {"a": 1}}, {"type": "ai-title", "aiTitle": 12345},
                user_rec([{"type": "text", "text": ["not", "a", "string"]}], cwd={"x": 1}),
            ])
            write_jsonl(Path(projects) / "-p", "good0000-0000.jsonl", [{"type": "ai-title", "aiTitle": "good"}])
            out = io.StringIO()
            with mock.patch.object(transcript, "PROJECTS_DIR", Path(projects)), contextlib.redirect_stdout(out):
                render_session.main(["list", "--all", "--lang", "en"])
        self.assertIn("bad00000-0000", out.getvalue())
        self.assertIn("good0000-0000", out.getvalue())


if __name__ == "__main__":
    unittest.main()
