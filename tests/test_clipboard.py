"""Tests for reading formatted (HTML) text from the clipboard on every system."""

import os
import sys
import unittest
from unittest import mock

from autotyper import clipboard
from autotyper.clipboard import (
    decode_html_bytes,
    decode_x11_selection,
    fragment_from_cf_html,
    read_clipboard_html,
    read_macos_html,
    read_windows_html,
    read_x11_html,
)

HTML = (
    '<b style="font-weight:normal"><p><span style="font-weight:700">Bold</span> café ✓ 😀</p></b>'
)
HTML_FORMAT_ID = 49384
CLIPBOARD_HANDLE = 0x5000
LOCKED_POINTER = 0x7000


def make_cf_html(fragment):
    """A CF_HTML payload with correct byte offsets, as Windows browsers write it."""
    template = (
        "Version:0.9\r\nStartHTML:{0:010d}\r\nEndHTML:{1:010d}\r\n"
        "StartFragment:{2:010d}\r\nEndFragment:{3:010d}\r\n"
    )
    header_length = len(template.format(0, 0, 0, 0).encode())
    before = b"<html><body>\r\n<!--StartFragment-->"
    after = b"<!--EndFragment-->\r\n</body></html>"
    body = fragment.encode("utf-8")
    start_fragment = header_length + len(before)
    end_fragment = start_fragment + len(body)
    end_html = end_fragment + len(after)
    header = template.format(header_length, end_html, start_fragment, end_fragment).encode()
    return header + before + body + after


class DecodeBytes(unittest.TestCase):
    def test_utf8(self):
        self.assertEqual(decode_html_bytes(HTML.encode("utf-8")), HTML)

    def test_utf8_with_bom(self):
        self.assertEqual(decode_html_bytes(b"\xef\xbb\xbf" + HTML.encode("utf-8")), HTML)

    def test_utf16_with_bom(self):
        self.assertEqual(decode_html_bytes(HTML.encode("utf-16")), HTML)

    def test_utf16_little_endian_without_bom(self):
        self.assertEqual(decode_html_bytes(HTML.encode("utf-16-le")), HTML)

    def test_trailing_nul_bytes_are_dropped(self):
        self.assertEqual(decode_html_bytes(b"<p>x</p>\x00\x00"), "<p>x</p>")

    def test_invalid_bytes_are_replaced_not_fatal(self):
        self.assertEqual(decode_html_bytes(b"<p>\xff\xfeok"[:3] + b"\xc3"), "<p>�")


class X11Selection(unittest.TestCase):
    def test_hex_byte_list_from_tk_is_turned_back_into_text(self):
        value = " ".join(hex(byte) for byte in HTML.encode("utf-8"))
        self.assertEqual(decode_x11_selection(value), HTML)

    def test_text_from_tk_is_returned_unchanged(self):
        self.assertEqual(decode_x11_selection("<b>already text</b>"), "<b>already text</b>")

    def test_reader_returns_none_when_nothing_formatted_was_copied(self):
        import tkinter

        root = mock.Mock()
        root.clipboard_get.side_effect = tkinter.TclError("CLIPBOARD selection doesn't exist")
        self.assertIsNone(read_x11_html(root))

    def test_reader_asks_tk_for_the_html_target(self):
        root = mock.Mock()
        root.clipboard_get.return_value = "<i>x</i>"
        self.assertEqual(read_x11_html(root), "<i>x</i>")
        root.clipboard_get.assert_called_once_with(type="text/html")


class CfHtml(unittest.TestCase):
    def test_fragment_is_cut_out_by_byte_offsets(self):
        self.assertEqual(fragment_from_cf_html(make_cf_html(HTML)), HTML)

    def test_whole_html_is_used_when_fragment_offsets_are_missing(self):
        data = b"Version:0.9\r\nStartHTML:0000000055\r\nEndHTML:0000000067\r\n<p>whole</p>"
        self.assertEqual(fragment_from_cf_html(data), "<p>whole</p>")

    def test_markup_after_the_header_is_used_when_offsets_are_nonsense(self):
        data = b"Version:0.9\r\nStartFragment:9999\r\nEndFragment:1\r\n<p>fallback</p>"
        self.assertEqual(fragment_from_cf_html(data), "<p>fallback</p>")


class FakeUser32:
    def __init__(self, available=True, opens=True, handle=CLIPBOARD_HANDLE):
        self.available = available
        self.opens = opens
        self.handle = handle
        self.closed = 0

    def RegisterClipboardFormatW(self, name):
        return HTML_FORMAT_ID if name == "HTML Format" else 0

    def IsClipboardFormatAvailable(self, format_id):
        return self.available and format_id == HTML_FORMAT_ID

    def OpenClipboard(self, _owner):
        return self.opens

    def GetClipboardData(self, format_id):
        return self.handle if format_id == HTML_FORMAT_ID else None

    def CloseClipboard(self):
        self.closed += 1
        return True


class FakeKernel32:
    def __init__(self, data, locks=True):
        self.data = data
        self.locks = locks
        self.unlocked = 0

    def GlobalLock(self, handle):
        return LOCKED_POINTER if self.locks and handle == CLIPBOARD_HANDLE else None

    def GlobalSize(self, handle):
        return len(self.data)

    def GlobalUnlock(self, handle):
        self.unlocked += 1
        return True


class WindowsClipboard(unittest.TestCase):
    def read(self, user32, kernel32):
        def string_at(pointer, size):
            self.assertEqual(pointer, LOCKED_POINTER)
            return kernel32.data[:size]

        return read_windows_html(user32, kernel32, string_at)

    def test_reads_the_html_fragment(self):
        user32, kernel32 = FakeUser32(), FakeKernel32(make_cf_html(HTML))
        self.assertEqual(self.read(user32, kernel32), HTML)
        self.assertEqual((user32.closed, kernel32.unlocked), (1, 1))

    def test_no_html_on_the_clipboard(self):
        user32 = FakeUser32(available=False)
        self.assertIsNone(self.read(user32, FakeKernel32(b"")))
        self.assertEqual(user32.closed, 0)

    def test_clipboard_that_cannot_be_opened_is_logged(self):
        with self.assertLogs("autotyper.clipboard", "WARNING"):
            self.assertIsNone(self.read(FakeUser32(opens=False), FakeKernel32(b"")))

    def test_missing_data_handle_still_closes_the_clipboard(self):
        user32 = FakeUser32(handle=None)
        self.assertIsNone(self.read(user32, FakeKernel32(b"")))
        self.assertEqual(user32.closed, 1)

    def test_memory_that_cannot_be_locked_still_closes_the_clipboard(self):
        user32 = FakeUser32()
        self.assertIsNone(self.read(user32, FakeKernel32(make_cf_html(HTML), locks=False)))
        self.assertEqual(user32.closed, 1)


class FakePasteboard:
    def __init__(self, html):
        self.html = html
        self.asked = []

    def stringForType_(self, kind):
        self.asked.append(kind)
        return self.html


class MacClipboard(unittest.TestCase):
    def appkit(self, html):
        board = FakePasteboard(html)
        pasteboard_class = mock.Mock()
        pasteboard_class.generalPasteboard.return_value = board
        return mock.Mock(NSPasteboard=pasteboard_class), board

    def test_reads_public_html(self):
        appkit, board = self.appkit(HTML)
        self.assertEqual(read_macos_html(appkit), HTML)
        self.assertEqual(board.asked, ["public.html"])

    def test_no_html_on_the_pasteboard(self):
        appkit, _board = self.appkit(None)
        self.assertIsNone(read_macos_html(appkit))

    def test_missing_pyobjc_is_logged_and_gives_none(self):
        with mock.patch.object(
            clipboard.importlib, "import_module", side_effect=ImportError("no AppKit")
        ), self.assertLogs("autotyper.clipboard", "WARNING"):
            self.assertIsNone(read_macos_html())


class Dispatch(unittest.TestCase):
    def test_each_system_uses_its_own_reader(self):
        root = object()
        cases = {
            "win32": "read_windows_html",
            "darwin": "read_macos_html",
            "linux": "read_x11_html",
        }
        for platform, reader in cases.items():
            with mock.patch.object(clipboard, reader, return_value="<b>x</b>") as read:
                self.assertEqual(read_clipboard_html(root, platform), "<b>x</b>")
            read.assert_called_once()

    def test_defaults_to_the_running_system(self):
        with mock.patch.object(clipboard, "read_x11_html", return_value="x") as read, mock.patch(
            "sys.platform", "linux"
        ):
            self.assertEqual(read_clipboard_html(object()), "x")
        read.assert_called_once()


CAN_OWN_X11_CLIPBOARD = sys.platform.startswith("linux") and bool(os.environ.get("DISPLAY"))


@unittest.skipUnless(CAN_OWN_X11_CLIPBOARD, "needs Linux with an X display")
class RealX11Clipboard(unittest.TestCase):
    """A browser-like owner serves raw UTF-8 text/html; Tk must read it back exactly."""

    def test_tk_reads_utf8_html_with_accents_and_emoji(self):
        import tkinter

        try:
            from tests.x11_helpers import HtmlClipboardOwner
        except ImportError as exc:
            self.skipTest(f"python-xlib is not installed: {exc}")
        with HtmlClipboardOwner(HTML):
            root = tkinter.Tk()
            self.addCleanup(root.destroy)
            root.withdraw()
            self.assertEqual(read_clipboard_html(root, "linux"), HTML)


if __name__ == "__main__":
    unittest.main(verbosity=2)
