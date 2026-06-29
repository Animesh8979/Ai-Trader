#!/usr/bin/env python
"""Run the Godmode setup wizard.

Usage:  py scripts/setup_wizard.py
(Works even before `pip install -e .` by adding src/ to the path.)
"""

import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from godmode.onboarding import run_setup_wizard  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_setup_wizard())
