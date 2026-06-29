#!/usr/bin/env python
"""Run the Godmode connectivity smoke test.

Usage:  py scripts/smoke_test.py
(Works even before `pip install -e .` by adding src/ to the path.)
"""

import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from godmode.diagnostics import run_smoke_test  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_smoke_test())
