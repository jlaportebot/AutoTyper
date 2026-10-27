"""Package entry point: ``python -m autotyper``."""

import sys


def main():
    """Launch the AutoTyper GUI."""
    if sys.platform != "win32":
        print("AutoTyper only runs on Windows.")
        print("Source: https://github.com/jlaportebot/AutoTyper")
        return 1
    from .gui import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
