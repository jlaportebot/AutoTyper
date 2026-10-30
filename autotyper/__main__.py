"""Package entry point: ``python -m autotyper``."""

import argparse
import sys

from .errors import InputBackendError
from .input_factory import BACKEND_MACOS, backend_name, create_backend

SMOKE_OK = "AUTOTYPER_SMOKE_OK"
SMOKE_FAIL = "AUTOTYPER_SMOKE_FAIL"


def _accessibility_trusted():
    """True if macOS lets this process send input; never shows the permission prompt."""
    from .mac_input import accessibility_trusted

    return accessibility_trusted()


def _smoke_backend():
    """Load the platform backend for the smoke test; returns ``(backend, note)``.

    On macOS a build without the Accessibility permission would make the real
    backend raise its prompt, so a placeholder is used and the state is reported.
    """
    if backend_name() != BACKEND_MACOS:
        return create_backend(), ""
    if not _accessibility_trusted():
        return object(), "accessibility=missing"
    return create_backend(), "accessibility=granted"


def _smoke_failed(error):
    """Print the failure marker with its reason; returns the failing exit code."""
    print(f"{SMOKE_FAIL}: {error}")
    return 1


def smoke_test():
    """Start the UI briefly and report that the build is healthy.

    Prints ``AUTOTYPER_SMOKE_OK`` and returns 0 when the platform backend loads
    and the window can be created; otherwise prints ``AUTOTYPER_SMOKE_FAIL:
    <reason>`` and returns 1. Nothing is typed or clicked.
    """
    try:
        import tkinter

        from .gui import AutoTyperApp
    except ImportError as error:
        return _smoke_failed(error)
    try:
        backend, note = _smoke_backend()
        app = AutoTyperApp(backend)
        app.root.update_idletasks()
        app.root.destroy()
    except (InputBackendError, ImportError, tkinter.TclError) as error:
        return _smoke_failed(error)
    details = [f"platform={sys.platform}", f"backend={backend_name()}"]
    print(" ".join([SMOKE_OK, *details, *([note] if note else [])]))
    return 0


def main(argv=None):
    """Launch the AutoTyper GUI on any supported operating system."""
    parser = argparse.ArgumentParser(prog="AutoTyper", description="Human-paced text entry.")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="check the build starts, print AUTOTYPER_SMOKE_OK and exit",
    )
    options, _ignored = parser.parse_known_args(argv)
    if options.smoke_test:
        return smoke_test()
    from .gui import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
