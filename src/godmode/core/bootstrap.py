"""Process bootstrap helpers.

Windows consoles often default to a legacy code page (cp1252), which turns Unicode like
em-dashes and the ✓/✗/⚠ status marks into garbage. Forcing UTF-8 on stdout/stderr makes
the CLI, wizard, and smoke-test output render correctly everywhere. Safe no-op elsewhere.
"""

from __future__ import annotations

import sys

_DONE = False


def ensure_utf8_console() -> None:
    global _DONE
    if _DONE:
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass  # already wrapped (e.g. pytest capture) or not reconfigurable
    _DONE = True
