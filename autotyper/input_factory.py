"""Chooses the input backend that matches the running operating system."""

import sys

from .errors import InputBackendError

BACKEND_WINDOWS = "windows"
BACKEND_MACOS = "macos"
BACKEND_LINUX = "linux"
BACKEND_UNSUPPORTED = "unsupported"
XLIB_PACKAGE = "python-xlib"


def backend_name():
    """Name of the backend for this OS: windows, macos, linux or unsupported."""
    if sys.platform == "win32":
        return BACKEND_WINDOWS
    if sys.platform == "darwin":
        return BACKEND_MACOS
    if sys.platform.startswith("linux"):
        return BACKEND_LINUX
    return BACKEND_UNSUPPORTED


def _create_linux_backend():
    """Start the X11 backend, explaining how to install python-xlib if it is missing."""
    try:
        from .linux_input import LinuxInput
    except ImportError as exc:
        raise InputBackendError(
            f"AutoTyper needs the {XLIB_PACKAGE} package on Linux ({exc}). "
            f"Install it with: pip install {XLIB_PACKAGE}"
        ) from exc
    return LinuxInput()


def create_backend():
    """Return the input backend for the current operating system."""
    name = backend_name()
    if name == BACKEND_WINDOWS:
        from .win_input import WindowsInput

        return WindowsInput()
    if name == BACKEND_MACOS:
        from .mac_input import MacInput

        return MacInput()
    if name == BACKEND_LINUX:
        return _create_linux_backend()
    raise InputBackendError(
        f"AutoTyper supports Windows, macOS and Linux, not '{sys.platform}'."
    )
