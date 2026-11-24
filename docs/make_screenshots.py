#!/usr/bin/env python3
"""Generate the screenshots in docs/images/ from a made-up demo session.

Run from the repository root (macOS, Google Chrome installed):
    python3 docs/make_screenshots.py

The demo session below is fictional and contains no real data. Each language gets its own copy of the
conversation, so README.md shows English and README.ja.md shows Japanese. Set CHROME to use another
Chrome or Chromium binary.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "claude-code-session-viewer" / "scripts" / "render_session.py"
OUT_DIR = ROOT / "docs" / "images"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SESSION_ID = "5e551011-0000-4000-8000-00000000demo"

sys.dont_write_bytecode = True  # importing ccsv must not leave __pycache__ folders in the skill
sys.path.insert(0, str(SCRIPT.parent))
from ccsv import i18n  # noqa: E402

TEXT = {
    "en": {
        "title": "Fix slugify for titles with emoji",
        "ask": "The test for `slugify` fails when the title contains emoji. Can you fix it?",
        "thinking": "The failure is probably in how non-ASCII characters are filtered. Run the test first.",
        "look": "Let me run the failing test first.",
        "todo": ["Reproduce the failure", "Fix slugify", "Run the tests again"],
        "run_tests": "Run the text tests",
        "run_again": "Run the text tests again",
        "fixed": ("Fixed. `slugify` now drops characters that are not letters, digits or spaces "
                  "before joining the words, so emoji no longer leave stray hyphens.\n\n"
                  "| Test | Before | After |\n|---|---|---|\n| `test_slugify_emoji` | failed | passed |\n"
                  "| other tests (11) | passed | passed |"),
        "ask2": "Thanks! Could you check whether other functions have the same problem?",
        "agent_desc": "Find similar text helpers",
        "agent_prompt": "List the functions in src/ that build identifiers from user text, and say whether they filter emoji.",
        "agent_found": "Two functions build identifiers from user text: `make_anchor` (filters emoji) and `file_stem` (does not).",
        "final": ("One more function has the same problem:\n\n"
                  "- `make_anchor` in `src/text.py`: already safe\n"
                  "- `file_stem` in `src/files.py`: **keeps emoji**, so file names can contain them\n\n"
                  "Shall I apply the same fix to `file_stem`?"),
    },
    "ja": {
        "title": "絵文字を含むタイトルで slugify が失敗する問題の修正",
        "ask": "タイトルに絵文字が入っていると `slugify` のテストが失敗します。直してもらえますか？",
        "thinking": "ASCII 以外の文字の除き方に原因がありそう。まずテストを実行して確かめる。",
        "look": "まず失敗しているテストを実行します。",
        "todo": ["失敗を再現する", "slugify を直す", "テストを再実行する"],
        "run_tests": "文字列処理のテストを実行",
        "run_again": "文字列処理のテストを再実行",
        "fixed": ("直しました。`slugify` は単語をつなぐ前に、文字・数字・空白以外を取り除くようになったので、"
                  "絵文字があっても余分なハイフンが残りません。\n\n"
                  "| テスト | 修正前 | 修正後 |\n|---|---|---|\n| `test_slugify_emoji` | 失敗 | 成功 |\n"
                  "| その他のテスト（11 件） | 成功 | 成功 |"),
        "ask2": "ありがとう！ 他の関数にも同じ問題がないか確認してもらえますか？",
        "agent_desc": "似た処理の関数を探す",
        "agent_prompt": "src/ の中で、ユーザーの入力から識別子を作る関数を挙げ、絵文字を取り除いているか教えてください。",
        "agent_found": "ユーザーの入力から識別子を作る関数は 2 つ: `make_anchor`（絵文字を除いている）と `file_stem`（除いていない）。",
        "final": ("同じ問題のある関数がもう 1 つありました。\n\n"
                  "- `src/text.py` の `make_anchor`: 問題なし\n"
                  "- `src/files.py` の `file_stem`: **絵文字が残る**ため、ファイル名に絵文字が入りうる\n\n"
                  "`file_stem` にも同じ修正を入れましょうか？"),
    },
}


def ts(minute, second):
    return "2026-11-01T01:%02d:%02d.000Z" % (minute, second)


def usage(output, read):
    return {"input_tokens": 6, "cache_creation_input_tokens": 1800, "cache_read_input_tokens": read,
            "output_tokens": output}


def assistant(msg_id, when, blocks, model="claude-opus-5-5", effort="high", tokens=(400, 24000)):
    return {"type": "assistant", "timestamp": when, "effort": effort,
            "message": {"id": msg_id, "model": model, "role": "assistant", "usage": usage(*tokens), "content": blocks}}


def user(when, content, **extra):
    rec = {"type": "user", "timestamp": when, "message": {"role": "user", "content": content}}
    rec.update(extra)
    return rec


def result(when, tool_id, content, is_error=False):
    return user(when, [{"type": "tool_result", "tool_use_id": tool_id, "content": content, "is_error": is_error}])


def demo_session(tx):
    failing = ("F...........\nFAILED tests/test_text.py::test_slugify_emoji\n"
               "AssertionError: assert 'hello--world' == 'hello-world'\n1 failed, 11 passed in 0.08s")
    source = ("def slugify(title):\n    words = title.lower().split()\n"
              "    return \"-\".join(w.strip(\".,!?\") for w in words)\n")
    return [
        {"type": "ai-title", "aiTitle": tx["title"]},
        user(ts(0, 0), tx["ask"], cwd="/home/demo/example-app", gitBranch="fix-slugify", version="2.1.0"),
        assistant("d1", ts(0, 4), [{"type": "thinking", "thinking": tx["thinking"]},
                                   {"type": "text", "text": tx["look"]}]),
        assistant("d2", ts(0, 5), [{"type": "tool_use", "id": "t_todo", "name": "TodoWrite", "input": {"todos": [
            {"content": tx["todo"][0], "status": "completed"}, {"content": tx["todo"][1], "status": "in_progress"},
            {"content": tx["todo"][2], "status": "pending"}]}}], tokens=(120, 25000)),
        result(ts(0, 5), "t_todo", "ok"),
        assistant("d3", ts(0, 6), [{"type": "tool_use", "id": "t_test1", "name": "Bash",
                                    "input": {"command": "python3 -m pytest tests/test_text.py -q",
                                              "description": tx["run_tests"]}}], tokens=(90, 25500)),
        result(ts(0, 8), "t_test1", failing, is_error=True),
        assistant("d4", ts(0, 9), [{"type": "tool_use", "id": "t_read", "name": "Read",
                                    "input": {"file_path": "/home/demo/example-app/src/text.py"}}], tokens=(60, 26000)),
        result(ts(0, 9), "t_read", source),
        assistant("d5", ts(0, 12), [{"type": "tool_use", "id": "t_edit", "name": "Edit", "input": {
            "file_path": "/home/demo/example-app/src/text.py",
            "old_string": "    words = title.lower().split()",
            "new_string": "    kept = \"\".join(c for c in title.lower() if c.isalnum() or c.isspace())\n"
                          "    words = kept.split()"}}], tokens=(210, 26500)),
        result(ts(0, 12), "t_edit", "The file was updated."),
        assistant("d6", ts(0, 13), [{"type": "tool_use", "id": "t_test2", "name": "Bash",
                                     "input": {"command": "python3 -m pytest tests/test_text.py -q",
                                               "description": tx["run_again"]}}], tokens=(80, 27000)),
        result(ts(0, 15), "t_test2", "............\n12 passed in 0.07s"),
        assistant("d7", ts(0, 18), [{"type": "text", "text": tx["fixed"]}], tokens=(350, 27500)),
        user(ts(2, 0), tx["ask2"]),
        assistant("d8", ts(2, 3), [{"type": "tool_use", "id": "t_agent", "name": "Agent", "input": {
            "description": tx["agent_desc"], "subagent_type": "Explore", "prompt": tx["agent_prompt"]}}],
            tokens=(150, 28000)),
        result(ts(2, 40), "t_agent", tx["agent_found"]),
        assistant("d9", ts(2, 44), [{"type": "text", "text": tx["final"]}], tokens=(300, 28500)),
    ]


def subagent_session(tx):
    return [
        user(ts(2, 4), tx["agent_prompt"]),
        assistant("s1", ts(2, 10), [{"type": "tool_use", "id": "s_grep", "name": "Grep", "input": {
            "pattern": "def (make_anchor|file_stem|slugify)", "path": "src"}}],
            model="claude-haiku-5-5", effort="medium", tokens=(70, 9000)),
        result(ts(2, 11), "s_grep", "src/text.py:12:def make_anchor(text):\nsrc/files.py:30:def file_stem(name):"),
        assistant("s2", ts(2, 35), [{"type": "text", "text": tx["agent_found"]}],
                  model="claude-haiku-5-5", effort="medium", tokens=(120, 9500)),
    ]


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def chrome_screenshot(url, png, width, height):
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=2", "--user-data-dir=" + profile,
                        "--window-size=%d,%d" % (width, height), "--virtual-time-budget=2000",
                        "--screenshot=" + str(png), url],
                       check=True, capture_output=True, timeout=120)


def showcase(html, lang, dark=False):
    """Expand the first Claude bubble and open the Edit card, so the screenshot shows tool calls."""
    i18n.set_lang(lang)
    html = html.replace("msg assistant long collapsed", "msg assistant long", 1)
    html = html.replace('aria-expanded="false">%s<' % i18n.t("show_full"),
                        'aria-expanded="true">%s<' % i18n.t("collapse"), 1)
    html = html.replace('<details class="tool"><summary><span class="tool-name">Edit',
                        '<details class="tool" open><summary><span class="tool-name">Edit', 1)
    if dark:
        html = html.replace('<html lang="%s">' % lang, '<html lang="%s" data-theme="dark">' % lang, 1)
        # The phone shot starts at the conversation: the session facts (shown in the desktop shot) are hidden.
        # (Scrolling to an anchor is unreliable in headless screenshots.)
        html = html.replace("</head>", "<style>.facts { display: none; }</style></head>", 1)
    return html


def main():
    if not Path(CHROME).exists():
        sys.exit("Chrome not found: %s (set CHROME)" % CHROME)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for lang, tx in TEXT.items():
            session = tmp / lang / (SESSION_ID + ".jsonl")
            write_jsonl(session, demo_session(tx))
            sub = tmp / lang / SESSION_ID / "subagents"
            write_jsonl(sub / "agent-demo.jsonl", subagent_session(tx))
            (sub / "agent-demo.meta.json").write_text(json.dumps({"agentType": "Explore", "toolUseId": "t_agent"}),
                                                      encoding="utf-8")
            page = tmp / lang / "page.html"
            subprocess.run([sys.executable, "-B", str(SCRIPT), "render", str(session), "--lang", lang,
                            "--out", str(page)], check=True, capture_output=True)
            html = page.read_text(encoding="utf-8")

            desktop = tmp / lang / "desktop.html"
            desktop.write_text(showcase(html, lang), encoding="utf-8")
            chrome_screenshot(desktop.as_uri(), OUT_DIR / ("%s-desktop.png" % lang), 1280, 1350)

            # A 500px window (the narrowest headless Chrome allows) already gets the phone layout (<= 860px).
            phone = tmp / lang / "phone.html"
            phone.write_text(showcase(html, lang, dark=True), encoding="utf-8")
            png = OUT_DIR / ("%s-phone-dark.png" % lang)
            chrome_screenshot(phone.as_uri(), png, 500, 1000)
            print("wrote", OUT_DIR / ("%s-desktop.png" % lang), "and", png)


if __name__ == "__main__":
    main()
