"""Launcher for AutoTyper.

Kept at the repository root so ``Start AutoTyper.bat`` and the PyInstaller
build can both start the GUI without a console window.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from autotyper.__main__ import main  # noqa: E402  (path setup must happen first)

if __name__ == "__main__":
    sys.exit(main() or 0)
