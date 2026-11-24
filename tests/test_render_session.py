"""Tests for skills/claude-code-session-viewer/scripts/render_session.py.

Run from the repository root:
    python3 -m unittest discover -s tests
"""

import contextlib
import importlib.util
import io
import os
import re
import string
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "claude-code-session-viewer" / "scripts" / "render_session.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "00000000-0000-4000-8000-000000000001.jsonl"

spec = importlib.util.spec_from_file_location("render_session", SCRIPT)
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

JAPANESE_RE = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")


def placeholders(template):
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def base_keys(table):
    return {k for k in table if not k.endswith("_one")}


def render(lang):
    rs.set_lang(lang)
    builder = rs.Builder(FIXTURE)
    items = builder.build()
    page, _ = rs.render_page(builder, items)
    return builder, page


class MessagesTest(unittest.TestCase):
    def test_every_language_has_the_same_keys(self):
        reference = base_keys(rs.MESSAGES[rs.DEFAULT_LANG])
        for lang, table in rs.MESSAGES.items():
            with self.subTest(lang=lang):
                self.assertEqual(base_keys(table), reference)

    def test_plural_variants_have_a_base_key(self):
        for lang, table in rs.MESSAGES.items():
            for key in table:
                if key.endswith("_one"):
                    with self.subTest(lang=lang, key=key):
                        self.assertIn(key[: -len("_one")], table)

    def test_placeholders_match_across_languages(self):
        reference = rs.MESSAGES[rs.DEFAULT_LANG]
        for lang, table in rs.MESSAGES.items():
            for key, template in table.items():
                with self.subTest(lang=lang, key=key):
                    if key.endswith("_one"):
                        # The singular form may drop {n}, but must not need anything extra.
                        self.assertLessEqual(placeholders(template), placeholders(table[key[: -len("_one")]]))
                    else:
                        self.assertEqual(placeholders(template), placeholders(reference[key]))

    def test_template_and_javascript_keys_exist(self):
        used = set(re.findall(r"\{\{t:([a-z_]+)\}\}", rs.TEMPLATE)) | set(rs.JS_MESSAGE_KEYS)
        self.assertTrue(used)
        for lang, table in rs.MESSAGES.items():
            with self.subTest(lang=lang):
                self.assertEqual(used - set(table), set())

    def test_plural_selection(self):
        rs.set_lang("en")
        self.assertEqual(rs.t("result_lines", n=1), "Result (1 line)")
        self.assertEqual(rs.t("result_lines", n=2), "Result (2 lines)")
        rs.set_lang("ja")
        self.assertEqual(rs.t("result_lines", n=1), "結果（1 行）")

    def tearDown(self):
        rs.set_lang(rs.DEFAULT_LANG)


class RenderTest(unittest.TestCase):
    def tearDown(self):
        rs.set_lang(rs.DEFAULT_LANG)

    def test_english_output_has_no_japanese(self):
        _, page = render("en")
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
        _, page = render("ja")
        self.assertIn('<html lang="ja">', page)
        for expected in (
            "結果（2 行）",
            "会話を圧縮しました（手動・圧縮前 12,345 トークン）",
            "サブエージェントのやり取り（Explore・2 件",
            "トークン合計（サブエージェントを含む）",
            "全文を表示" if "long collapsed" in page else "目次",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)

    def test_internal_records_are_hidden(self):
        _, page = render("en")
        self.assertNotIn("internal note that must not be shown", page)

    def test_token_totals(self):
        builder, _ = render("en")
        # Six main responses (msg_1 is split over two records but counted once) plus one subagent response.
        self.assertEqual(builder.usage, {"input": 60, "cache_create": 600, "cache_read": 6000, "output": 300})
        self.assertEqual(builder.sub_usage, {"input": 5, "cache_create": 0, "cache_read": 200, "output": 20})
        self.assertEqual(builder.total_usage()["output"], 320)
        self.assertEqual(set(builder.usage_by_model), {"claude-opus-5-5", "claude-haiku-5-5"})


class LanguageDetectionTest(unittest.TestCase):
    def detect(self, env, platform="linux"):
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(rs.sys, "platform", platform):
            return rs.detect_lang()

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
        with mock.patch.object(rs.subprocess, "run", return_value=result):
            self.assertEqual(self.detect({"LANG": "C.UTF-8"}, platform="darwin"), "ja")


class CommandLineTest(unittest.TestCase):
    def tearDown(self):
        rs.set_lang(rs.DEFAULT_LANG)

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rs.main(list(argv))
        return out.getvalue()

    def test_lang_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            en = self.run_main("render", str(FIXTURE), "--lang", "en", "--out", tmp)
            self.assertIn("Wrote:", en)
            ja = self.run_main("render", str(FIXTURE), "--lang", "ja", "--out", tmp)
            self.assertIn("出力しました:", ja)
            self.assertEqual(len(list(Path(tmp).glob("*.html"))), 1)

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
                        rs.main(["--lang", lang, "--help"])
                finally:
                    self.assertIn(expected, out.getvalue())


if __name__ == "__main__":
    unittest.main()
