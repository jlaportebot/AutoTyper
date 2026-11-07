"""Read formatted (HTML) text from the system clipboard.

Every system keeps the formatted copy of copied text under its own name:
``text/html`` on X11, "HTML Format" (CF_HTML) on Windows and ``public.html``
on macOS. Each reader returns ``None`` when there is no HTML to read, so the
caller can fall back to an ordinary plain-text paste.
"""

import ctypes
import importlib
import logging
import re
import sys

logger = logging.getLogger(__name__)

X11_HTML_TARGET = "text/html"
WINDOWS_HTML_FORMAT = "HTML Format"
MACOS_HTML_TYPE = "public.html"
# Tk hands back clipboard data of unknown types as "0x3c 0x70 ..." byte lists.
TK_BYTE_LIST = re.compile(r"\s*(?:0x[0-9a-fA-F]{1,2}\s*)+")
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
NUL = b"\x00"
CF_HTML_FIRST_TAG = b"<"


def decode_html_bytes(data):
    """Text of HTML clipboard bytes: UTF-16 when it looks like it, otherwise UTF-8."""
    if data.startswith(UTF16_BOMS):
        text = data.decode("utf-16", errors="replace")
    elif data[1:2] == NUL:
        text = data.decode("utf-16-le", errors="replace")
    else:
        text = data.decode("utf-8-sig", errors="replace")
    return text.rstrip("\x00")


def decode_x11_selection(value):
    """HTML text from what Tk returned for the ``text/html`` clipboard target."""
    if TK_BYTE_LIST.fullmatch(value):
        return decode_html_bytes(bytes(int(token, 16) for token in value.split()))
    return value


def read_x11_html(root):
    """HTML on the X11 clipboard, read through the Tk root window."""
    import tkinter

    try:
        value = root.clipboard_get(type=X11_HTML_TARGET)
    except tkinter.TclError as exc:
        logger.debug("No formatted text on the clipboard: %s", exc)
        return None
    return decode_x11_selection(value)


def _cf_html_offset(data, name):
    """A byte offset from the CF_HTML header, such as ``StartFragment``."""
    match = re.search(name + rb":(\d+)", data)
    return int(match.group(1)) if match else None


def _slice_between(data, start_name, end_name):
    """``data[start:end]`` for two header offsets, or ``None`` if they are unusable."""
    start = _cf_html_offset(data, start_name)
    end = _cf_html_offset(data, end_name)
    if start is None or end is None or not 0 <= start <= end <= len(data):
        return None
    return data[start:end]


def fragment_from_cf_html(data):
    """The copied HTML inside a Windows CF_HTML payload (offsets are in bytes)."""
    piece = _slice_between(data, b"StartFragment", b"EndFragment")
    if piece is None:
        piece = _slice_between(data, b"StartHTML", b"EndHTML")
    if piece is None:
        first_tag = data.find(CF_HTML_FIRST_TAG)
        piece = data[max(0, first_tag) :]
    return piece.decode("utf-8", errors="replace").rstrip("\x00")


def _windows_api():
    """user32 and kernel32 with the argument and return types the clipboard needs."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = ctypes.c_void_p
    user32.RegisterClipboardFormatW.argtypes = (ctypes.c_wchar_p,)
    user32.RegisterClipboardFormatW.restype = ctypes.c_uint
    user32.IsClipboardFormatAvailable.argtypes = (ctypes.c_uint,)
    user32.OpenClipboard.argtypes = (handle,)
    user32.GetClipboardData.argtypes = (ctypes.c_uint,)
    user32.GetClipboardData.restype = handle
    kernel32.GlobalLock.argtypes = (handle,)
    kernel32.GlobalLock.restype = handle
    kernel32.GlobalUnlock.argtypes = (handle,)
    kernel32.GlobalSize.argtypes = (handle,)
    kernel32.GlobalSize.restype = ctypes.c_size_t
    return user32, kernel32


def _locked_bytes(handle, kernel32, string_at):
    """Copy the bytes of a clipboard memory handle."""
    if not handle:
        return None
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        return string_at(pointer, kernel32.GlobalSize(handle))
    finally:
        kernel32.GlobalUnlock(handle)


def read_windows_html(user32=None, kernel32=None, string_at=None):
    """HTML on the Windows clipboard ("HTML Format"), or ``None``."""
    if user32 is None or kernel32 is None:
        user32, kernel32 = _windows_api()
    string_at = string_at or ctypes.string_at
    html_format = user32.RegisterClipboardFormatW(WINDOWS_HTML_FORMAT)
    if not html_format or not user32.IsClipboardFormatAvailable(html_format):
        return None
    if not user32.OpenClipboard(None):
        logger.warning("Could not open the clipboard to read formatted text.")
        return None
    try:
        data = _locked_bytes(user32.GetClipboardData(html_format), kernel32, string_at)
    finally:
        user32.CloseClipboard()
    return fragment_from_cf_html(data) if data else None


def read_macos_html(appkit=None):
    """HTML on the macOS pasteboard (``public.html``), or ``None``."""
    if appkit is None:
        try:
            appkit = importlib.import_module("AppKit")
        except ImportError as exc:
            logger.warning("Cannot read formatted text without pyobjc AppKit: %s", exc)
            return None
    html = appkit.NSPasteboard.generalPasteboard().stringForType_(MACOS_HTML_TYPE)
    return str(html) if html else None


def read_clipboard_html(root, platform=None):
    """HTML on the clipboard of the running system, or ``None`` if there is none."""
    platform = platform or sys.platform
    if platform == "win32":
        return read_windows_html()
    if platform == "darwin":
        return read_macos_html()
    return read_x11_html(root)
