"""Current language, message lookup and OS language detection."""

import os
import re
import subprocess
import sys

from .messages import MESSAGES

SUPPORTED_LANGS = tuple(MESSAGES)
DEFAULT_LANG = SUPPORTED_LANGS[0]

_lang = DEFAULT_LANG


def set_lang(lang):
    global _lang
    _lang = lang if lang in MESSAGES else DEFAULT_LANG


def get_lang():
    return _lang


def t(key, **kw):
    """Look up a message in the current language and fill in its placeholders.

    When n == 1 and the language defines "<key>_one", that singular form is used instead.
    """
    table = MESSAGES[_lang]
    if kw.get("n") == 1 and key + "_one" in table:
        key += "_one"
    template = table.get(key) or MESSAGES[DEFAULT_LANG][key]
    return template.format(**kw)


def lang_from_locale_name(name):
    """Map a locale name such as "ja_JP.UTF-8" or "en-US" to a supported language, or None."""
    name = (name or "").strip().strip('"').lower()
    if not name or name in ("c", "posix") or name.startswith(("c.", "posix.")):
        return None  # these do not name a language
    return "ja" if name.startswith("ja") else "en"


def detect_lang():
    """Language used when --lang is not given: OS locale first, then English."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        lang = lang_from_locale_name(os.environ.get(var))
        if lang:
            return lang
    if sys.platform == "darwin":
        # macOS apps often run with LANG unset or set to C; read the system language instead.
        try:
            out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"],
                                 capture_output=True, text=True, timeout=3).stdout
            m = re.search(r'"?([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*)"?', out.replace("(", " "))
            if m:
                lang = lang_from_locale_name(m.group(1))
                if lang:
                    return lang
        except (OSError, subprocess.SubprocessError):
            pass
    return DEFAULT_LANG
