"""User-visible strings for every supported language.

To add a language: create <language code>.py (e.g. fr.py) with a MESSAGES dict that has the same
keys as en.py, then register it below.
"""

from . import en, ja

# The first entry is the default language.
MESSAGES = {
    "en": en.MESSAGES,
    "ja": ja.MESSAGES,
}
