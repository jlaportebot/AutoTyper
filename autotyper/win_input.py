"""Keyboard input layer for Windows (SendInput via ctypes).

Everything Windows-specific lives here so the engine can be unit tested on
any platform with a fake backend.
"""

import ctypes
import time

from .keys import KEY_ESCAPE, KEY_F9, KEY_LEFT_BUTTON

VK_RETURN = 0x0D
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_LBUTTON = 0x01
VK_F9 = 0x78
VK_MENU = 0x12

SYMBOLIC_TO_VK = {
    KEY_ESCAPE: VK_ESCAPE,
    KEY_F9: VK_F9,
    KEY_LEFT_BUTTON: VK_LBUTTON,
}

GA_ROOT = 2
SW_RESTORE = 9
MAX_TITLE_CHARS = 256


def build_input_structs(ctypes_module=None):
    """Build the SendInput structures with correct platform field sizes."""
    ctypes_module = ctypes_module or ctypes
    LONG, DWORD, WORD = ctypes_module.c_int32, ctypes_module.c_uint32, ctypes_module.c_uint16
    ULONG_PTR = ctypes_module.c_size_t

    class MOUSEINPUT(ctypes_module.Structure):
        _fields_ = [
            ("dx", LONG),
            ("dy", LONG),
            ("mouseData", DWORD),
            ("dwFlags", DWORD),
            ("time", DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes_module.Structure):
        _fields_ = [
            ("wVk", WORD),
            ("wScan", WORD),
            ("dwFlags", DWORD),
            ("time", DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes_module.Structure):
        _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]

    class _U(ctypes_module.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes_module.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", DWORD), ("u", _U)]

    return INPUT, KEYBDINPUT, MOUSEINPUT


class WindowsInput:
    """Sends real keystrokes and mouse clicks to the Windows desktop."""

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    KEYUP = 0x0002
    UNICODE = 0x0004
    LEFTDOWN = 0x0002
    LEFTUP = 0x0004

    def __init__(self):
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wt = wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._enable_dpi_awareness()
        self.INPUT, self.KEYBDINPUT, self.MOUSEINPUT = build_input_structs(ctypes)
        self._declare_api(wintypes)

    def _enable_dpi_awareness(self):
        """Report true pixel coordinates to the OS so clicks land accurately."""
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                self.user32.SetProcessDPIAware()
            except Exception:
                pass

    def _declare_api(self, wintypes):
        """Declare argument types and return values for the Win32 calls used."""
        api = self.user32
        api.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(self.INPUT), ctypes.c_int)
        api.SendInput.restype = wintypes.UINT
        api.WindowFromPoint.argtypes = (wintypes.POINT,)
        api.WindowFromPoint.restype = wintypes.HWND
        api.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        api.GetAncestor.restype = wintypes.HWND
        api.GetForegroundWindow.restype = wintypes.HWND
        api.SetForegroundWindow.argtypes = (wintypes.HWND,)
        api.IsIconic.argtypes = (wintypes.HWND,)
        api.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        api.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)

    def _send(self, *inputs):
        """Send a batch of INPUT structs, raising if Windows blocks them."""
        array = (self.INPUT * len(inputs))(*inputs)
        sent = self.user32.SendInput(len(inputs), array, self.ctypes.sizeof(self.INPUT))
        if sent != len(inputs):
            raise OSError(
                "Windows blocked the keystroke (target app may be running as administrator)"
            )

    def _key(self, vk=0, scan=0, flags=0):
        """Build a single keyboard INPUT struct."""
        item = self.INPUT(type=self.INPUT_KEYBOARD)
        item.ki = self.KEYBDINPUT(vk, scan, flags, 0, 0)
        return item

    def press_vk(self, vk):
        """Press and release a virtual key."""
        self._send(self._key(vk=vk), self._key(vk=vk, flags=self.KEYUP))

    def type_char(self, ch):
        """Type one character, including Unicode and surrogate pairs."""
        if ch == "\n":
            return self.press_vk(VK_RETURN)
        if ch == "\t":
            return self.press_vk(VK_TAB)
        if ch == "\r":
            return None
        data = ch.encode("utf-16-le")
        units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
        self._send(
            *[self._key(scan=unit, flags=self.UNICODE) for unit in units],
            *[self._key(scan=unit, flags=self.UNICODE | self.KEYUP) for unit in units],
        )

    def key_down(self, key):
        """True while a key is physically held down.

        ``key`` is a symbolic name from ``keys.py`` or a raw Win32 ``VK_*`` code.
        """
        vk = SYMBOLIC_TO_VK.get(key, key)
        if not isinstance(vk, int):
            raise ValueError(f"Unknown key: {key!r}")
        return bool(self.user32.GetAsyncKeyState(vk) & 0x8000)

    def cursor_pos(self):
        """Current mouse cursor position in screen pixels."""
        point = self.wt.POINT()
        self.user32.GetCursorPos(self.ctypes.byref(point))
        return point.x, point.y

    def root_window_at(self, x, y):
        """Top-level window handle under the given screen coordinates."""
        handle = self.user32.WindowFromPoint(self.wt.POINT(int(x), int(y)))
        return self.user32.GetAncestor(handle, GA_ROOT) if handle else None

    def window_title(self, hwnd):
        """Title bar text of a window handle."""
        buffer = self.ctypes.create_unicode_buffer(MAX_TITLE_CHARS)
        self.user32.GetWindowTextW(hwnd, buffer, MAX_TITLE_CHARS)
        return buffer.value

    def foreground(self):
        """Handle of the window that currently has keyboard focus."""
        return self.user32.GetForegroundWindow()

    def focus(self, hwnd):
        """Bring a window back to the foreground."""
        if not hwnd:
            return
        if self.user32.IsIconic(hwnd):
            self.user32.ShowWindow(hwnd, SW_RESTORE)
        self.press_vk(VK_MENU)
        self.user32.SetForegroundWindow(hwnd)

    def click(self, x, y):
        """Click the screen at the given coordinates."""
        self.user32.SetCursorPos(int(x), int(y))
        time.sleep(0.05)
        down = self.INPUT(type=self.INPUT_MOUSE)
        down.mi = self.MOUSEINPUT(0, 0, 0, self.LEFTDOWN, 0, 0)
        up = self.INPUT(type=self.INPUT_MOUSE)
        up.mi = self.MOUSEINPUT(0, 0, 0, self.LEFTUP, 0, 0)
        self._send(down, up)
