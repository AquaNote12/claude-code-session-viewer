#!/usr/bin/env python3
"""Convert a Claude Code session transcript (JSONL) into a standalone HTML page.

Usage:
  render_session.py list [--all] [--limit N] [--project DIR] [--current-session SESSION] [--lang ja|en]
  render_session.py render SESSION [--out PATH] [--no-subagents] [--no-tools] [--no-thinking] [--lang ja|en]
  render_session.py open PATH

SESSION is a session ID (a unique prefix is enough) or a path to a JSONL file.
When --lang is omitted, the language is taken from the OS locale, falling back to English.
Requires only the Python 3.9+ standard library. The implementation lives in the ccsv package
next to this file; this script only handles the command line.
"""

import argparse
import datetime as dt
import os
import sys
import webbrowser
from pathlib import Path

# Make the ccsv package importable even when Python runs with -I / -P or PYTHONSAFEPATH,
# which leave the script's directory out of sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ccsv.i18n import SUPPORTED_LANGS, detect_lang, set_lang, t  # noqa: E402
from ccsv.render import filter_items, is_generated_page, render_page  # noqa: E402
from ccsv.transcript import (  # noqa: E402
    Builder, SessionLookupError, all_session_files, peek_session, project_dir_name, resolve_session,
)
from ccsv.util import clean_line, fmt_num  # noqa: E402

DEFAULT_OUT_DIR = Path.home() / "Downloads" / "claude-code-sessions"


def list_scope(args):
    """Which project's sessions to list: (directory name under ~/.claude/projects, text shown to the user).

    Order: --project, then the project of --current-session, then the current directory. The current
    directory alone is not reliable inside Claude Code, because the shell may have moved elsewhere.
    """
    if args.project:
        return project_dir_name(Path(args.project).expanduser().resolve()), args.project
    if args.current_session:
        try:
            session = resolve_session(args.current_session)
            return session.parent.name, str(session.parent)
        except SessionLookupError:
            pass  # e.g. a brand-new session not written yet; fall back to the current directory
    cwd = os.getcwd()
    return project_dir_name(Path(cwd).resolve()), cwd


def cmd_list(args):
    files = all_session_files()
    if not args.all:
        target, shown = list_scope(args)
        scoped = [f for f in files if f.parent.name == target]
        if scoped:
            files = scoped
        else:
            print(t("list_fallback", dir=shown))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[: args.limit]:
        title, first, cwd = peek_session(f)
        mtime = dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        # Titles, prompts and paths come from transcripts: one line each, without control characters,
        # so they cannot rewrite the terminal or pose as separate lines of output (e.g. instructions to Claude).
        print("%s  %s  %s" % (clean_line(f.stem, 80), mtime, clean_line(title or first or t("untitled"), 60)))
        if args.all or cwd:
            print("    cwd: %s" % clean_line(cwd or f.parent.name, 200))


def output_path(out_arg, filename):
    """Where to write: a path ending in .html is the file itself; anything else is a directory to write into."""
    if not out_arg:
        return DEFAULT_OUT_DIR / filename
    out = Path(out_arg).expanduser()
    return out if out.suffix.lower() == ".html" else out / filename


def write_page(out, page):
    """Write the page readable by the owner only, without following a symbolic link at the destination."""
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        sys.exit(t("err_out_dir", path=out.parent, error=e.strerror or e))
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(out), flags, 0o600)
    except OSError as e:
        sys.exit(t("err_write", path=out, error=e.strerror or e))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)  # an existing file keeps its old mode otherwise
        f.write(page)


def cmd_render(args):
    try:
        path = resolve_session(args.session)
    except SessionLookupError as e:
        sys.exit(str(e))
    builder = Builder(path, include_subagents=not args.no_subagents)
    items = filter_items(builder.build(), include_tools=not args.no_tools, include_thinking=not args.no_thinking)
    page, filename = render_page(builder, items)
    out = output_path(args.out, filename)
    write_page(out, page)
    n = sum(1 for it in items if it["kind"] in ("user", "assistant"))
    print(t("rendered", path=out))
    print(t("source", path=path))
    print(t("stats", n=n, kb=fmt_num(len(page.encode("utf-8")) // 1024)))
    print(t("privacy_notice"))


GENERATED_PAGE_MARKER = b'<script id="ccsv-data" type="application/json">'


def cmd_open(args):
    # The browser is started by Python, not by a shell command, so nothing in the path is interpreted.
    # The skill may run this without asking, so it only opens pages that this version of the tool generated:
    # the real file (after following symbolic links) must be an .html file whose head and scripts match the
    # template exactly, so that its Content-Security-Policy lets nothing but this version's app.js run.
    # A data-block marker alone is not enough: anyone can write it into a page of their own.
    path = Path(args.path).expanduser()
    try:
        real = path.resolve(strict=True)
    except (OSError, RuntimeError):
        sys.exit(t("err_open", path=args.path))
    if real.suffix.lower() != ".html" or not real.is_file():
        sys.exit(t("err_open", path=args.path))
    try:
        data = real.read_bytes()
        generated = GENERATED_PAGE_MARKER in data and is_generated_page(data.decode("utf-8", errors="replace"))
    except OSError:
        generated = False
    if not generated:
        sys.exit(t("err_open_not_generated", path=args.path))
    webbrowser.open(real.as_uri())
    print(t("opened", path=path))


def build_parser():
    ap = argparse.ArgumentParser(description=t("cli_description"))
    lang_help = t("cli_lang")
    # --lang is accepted both before and after the subcommand. main() reads it with a pre-parser,
    # so the value argparse stores here is not used.
    ap.add_argument("--lang", choices=SUPPORTED_LANGS, help=lang_help)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("list", help=t("cli_list"))
    lp.add_argument("--all", action="store_true", help=t("cli_all"))
    lp.add_argument("--project", help=t("cli_project"))
    lp.add_argument("--current-session", metavar="SESSION", help=t("cli_current_session"))
    lp.add_argument("--limit", type=int, default=15, help=t("cli_limit"))
    lp.add_argument("--lang", choices=SUPPORTED_LANGS, help=lang_help)
    rp = sub.add_parser("render", help=t("cli_render"))
    rp.add_argument("session", help=t("cli_session"))
    rp.add_argument("--out", help=t("cli_out", path=DEFAULT_OUT_DIR))
    rp.add_argument("--no-subagents", action="store_true", help=t("cli_no_subagents"))
    rp.add_argument("--no-tools", action="store_true", help=t("cli_no_tools"))
    rp.add_argument("--no-thinking", action="store_true", help=t("cli_no_thinking"))
    rp.add_argument("--lang", choices=SUPPORTED_LANGS, help=lang_help)
    op = sub.add_parser("open", help=t("cli_open"))
    op.add_argument("path", help=t("cli_open_path"))
    op.add_argument("--lang", choices=SUPPORTED_LANGS, help=lang_help)
    return ap


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # Pick the language before building the parser, so that --help is localized as well.
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--lang", choices=SUPPORTED_LANGS)
    known, _ = pre_parser.parse_known_args(argv)
    set_lang(known.lang or detect_lang())
    args = build_parser().parse_args(argv)
    {"list": cmd_list, "render": cmd_render, "open": cmd_open}[args.cmd](args)


if __name__ == "__main__":
    main()
