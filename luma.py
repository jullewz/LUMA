#!/usr/bin/env python3
"""Luma – liquid-glass media player.  Run:  python luma.py [files...]"""
import os
import sys

if sys.version_info < (3, 9):
    sys.exit("Luma needs Python 3.9 or newer: https://www.python.org/downloads/")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util  # noqa: E402

if importlib.util.find_spec("PySide6") is None:
    sys.exit("Luma needs PySide6. Install the requirements first:\n"
             "    python -m pip install -r requirements.txt")

from luma.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
