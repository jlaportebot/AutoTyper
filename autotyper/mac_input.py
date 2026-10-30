"""Keyboard and mouse input for macOS (Quartz event services via pyobjc).

Everything macOS-specific lives here. Quartz and AppKit are only imported when
a :class:`MacInput` needs them, and both can be injected so the logic is
testable on any platform.
"""

import importlib
import logging
import time

from .errors import InputBackendError
from .keys import KEY_ESCAPE, KEY_F9, KEY_LEFT_BUTTON

logger = logging.getLogger(__name__)

KEYCODE_RETURN = 36
KEYCODE_TAB = 48
KEYCODE_SPACE = 49
KEYCODE_ESCAPE = 53
KEYCODE_F9 = 101
UNICODE_KEYCODE = 0
BYTES_PER_UTF16_UNIT = 2
CLICK_SETTLE_DELAY = 0.05
CLICK_HOLD_DELAY = 0.03
NORMAL_WINDOW_LAYER = 0

KEY_KEYCODES = {KEY_ESCAPE: KEYCODE_ESCAPE, KEY_F9: KEYCODE_F9}
CONTROL_KEYCODES = {"\n": KEYCODE_RETURN, "\t": KEYCODE_TAB}

WINDOW_NUMBER = "kCGWindowNumber"
WINDOW_NAME = "kCGWindowName"
WINDOW_OWNER_NAME = "kCGWindowOwnerName"
WINDOW_OWNER_PID = "kCGWindowOwnerPID"
WINDOW_BOUNDS = "kCGWindowBounds"
WINDOW_LAYER = "kCGWindowLayer"
PROMPT_OPTION = "AXTrustedCheckOptionPrompt"

QUARTZ_PACKAGE = "pyobjc-framework-Quartz"
APPKIT_PACKAGE = "pyobjc-framework-Cocoa"
APPLICATION_SERVICES_PACKAGE = "pyobjc-framework-ApplicationServices"
# pyobjc keeps the Accessibility functions in HIServices, which ApplicationServices
# re-exports; Quartz does not have them, but is tried in case a future pyobjc does.
ACCESSIBILITY_MODULES = ("ApplicationServices", "Quartz")
ACCESSIBILITY_FUNCTIONS = ("AXIsProcessTrusted", "AXIsProcessTrustedWithOptions")
ACCESSIBILITY_MESSAGE = (
    "AutoTyper needs Accessibility permission. Open System Settings → Privacy & "
    "Security → Accessibility and enable AutoTyper, then restart the app."
)


class AccessibilityPermissionError(InputBackendError):
    """macOS has not allowed this app to send synthetic input."""


def utf16_length(text):
    """Number of UTF-16 code units in ``text`` (what Quartz expects)."""
    return len(text.encode("utf-16-le")) // BYTES_PER_UTF16_UNIT


def _load_framework(module_name, package):
    """Import a pyobjc framework, explaining how to install it if missing."""
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise InputBackendError(
            f"AutoTyper needs the {package} package on macOS. "
            f"Install it with: pip install {package}"
        ) from exc


def _offers_accessibility(module):
    """True if the module exposes the Accessibility trust functions."""
    return all(hasattr(module, name) for name in ACCESSIBILITY_FUNCTIONS)


def find_accessibility_module():
    """The pyobjc module that provides AXIsProcessTrusted, ApplicationServices first."""
    for name in ACCESSIBILITY_MODULES:
        try:
            module = importlib.import_module(name)
        except ImportError as exc:
            logger.debug("Could not import %s for the Accessibility check: %s", name, exc)
            continue
        if _offers_accessibility(module):
            return module
    raise InputBackendError(
        f"AutoTyper needs the {APPLICATION_SERVICES_PACKAGE} package on macOS. "
        f"Install it with: pip install {APPLICATION_SERVICES_PACKAGE}"
    )


def accessibility_trusted(accessibility=None):
    """True if macOS lets this process send synthetic keyboard and mouse input.

    ``accessibility`` is a module with ``AXIsProcessTrusted``; by default it is found
    with :func:`find_accessibility_module`.
    """
    if accessibility is None:
        accessibility = find_accessibility_module()
    return bool(accessibility.AXIsProcessTrusted())


def _bounds_rect(bounds):
    """``(left, top, width, height)`` of a window bounds value."""
    if hasattr(bounds, "origin"):
        return bounds.origin.x, bounds.origin.y, bounds.size.width, bounds.size.height
    return bounds["X"], bounds["Y"], bounds["Width"], bounds["Height"]


def _window_contains(window, x, y):
    """True if the screen point lies inside the window's bounds."""
    bounds = window.get(WINDOW_BOUNDS)
    if bounds is None:
        return False
    left, top, width, height = _bounds_rect(bounds)
    return left <= x < left + width and top <= y < top + height


class MacInput:
    """Sends real keystrokes and mouse clicks to the macOS desktop."""

    def __init__(self, quartz=None, appkit=None, accessibility=None):
        injected = quartz is not None
        self.quartz = quartz if injected else _load_framework("Quartz", QUARTZ_PACKAGE)
        self._appkit = appkit
        if accessibility is None:
            accessibility = self.quartz if injected else find_accessibility_module()
        self._require_accessibility(accessibility)

    @staticmethod
    def _require_accessibility(accessibility):
        """Raise an actionable error unless synthetic input is permitted."""
        if accessibility_trusted(accessibility):
            return
        accessibility.AXIsProcessTrustedWithOptions({PROMPT_OPTION: True})
        raise AccessibilityPermissionError(ACCESSIBILITY_MESSAGE)

    def _appkit_module(self):
        """AppKit, imported the first time a window needs activating."""
        if self._appkit is None:
            self._appkit = _load_framework("AppKit", APPKIT_PACKAGE)
        return self._appkit

    def _post(self, event, description):
        """Post an event to the HID tap; fail loudly if macOS refused to build it."""
        if event is None:
            raise OSError(f"macOS could not create a {description} event.")
        self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, event)

    def _post_key(self, keycode, key_down, text=None):
        """Post one key press or release, optionally carrying literal text."""
        event = self.quartz.CGEventCreateKeyboardEvent(None, keycode, key_down)
        if event is not None and text is not None:
            self.quartz.CGEventKeyboardSetUnicodeString(event, utf16_length(text), text)
        self._post(event, "keyboard")

    def _tap(self, keycode, text=None):
        """Press and release a key."""
        self._post_key(keycode, True, text)
        self._post_key(keycode, False, text)

    def type_char(self, ch):
        """Type one character, including Unicode and surrogate pairs."""
        if ch == "\r":
            return
        if ch in CONTROL_KEYCODES:
            self._tap(CONTROL_KEYCODES[ch])
            return
        self._tap(UNICODE_KEYCODE, ch)

    def key_down(self, key):
        """True while the named key (see ``keys.py``) is physically held."""
        quartz = self.quartz
        state = quartz.kCGEventSourceStateHIDSystemState
        if key == KEY_LEFT_BUTTON:
            return bool(quartz.CGEventSourceButtonState(state, quartz.kCGMouseButtonLeft))
        if key not in KEY_KEYCODES:
            raise ValueError(f"Unknown key: {key!r}")
        return bool(quartz.CGEventSourceKeyState(state, KEY_KEYCODES[key]))

    def _window_list(self):
        """On-screen windows, frontmost first."""
        quartz = self.quartz
        options = (
            quartz.kCGWindowListOptionOnScreenOnly | quartz.kCGWindowListExcludeDesktopElements
        )
        return list(quartz.CGWindowListCopyWindowInfo(options, quartz.kCGNullWindowID) or [])

    def _normal_windows(self):
        """Application windows, frontmost first (no menu bar, Dock or overlays)."""
        return [
            window
            for window in self._window_list()
            if window.get(WINDOW_LAYER, NORMAL_WINDOW_LAYER) == NORMAL_WINDOW_LAYER
        ]

    def _find_window(self, handle):
        """The window-list entry for a window number, or None."""
        for window in self._window_list():
            if window.get(WINDOW_NUMBER) == handle:
                return window
        return None

    def foreground(self):
        """Window number of the frontmost application window."""
        windows = self._normal_windows()
        return windows[0].get(WINDOW_NUMBER) if windows else None

    def root_window_at(self, x, y):
        """Window number of the frontmost window under the given screen point."""
        for window in self._normal_windows():
            if _window_contains(window, x, y):
                return window.get(WINDOW_NUMBER)
        return None

    def window_title(self, handle):
        """Window name, else its application's name, else an empty string."""
        window = self._find_window(handle)
        if window is None:
            return ""
        return window.get(WINDOW_NAME) or window.get(WINDOW_OWNER_NAME) or ""

    def focus(self, handle):
        """Bring the application that owns a window back to the foreground."""
        window = self._find_window(handle)
        if window is None:
            return
        appkit = self._appkit_module()
        pid = window.get(WINDOW_OWNER_PID)
        application = appkit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if application is None:
            logger.debug("Process %s is no longer running; cannot focus it", pid)
            return
        application.activateWithOptions_(appkit.NSApplicationActivateIgnoringOtherApps)

    def same_application(self, first, second):
        """True if two window numbers belong to the same application process."""
        windows = (self._find_window(first), self._find_window(second))
        if None in windows:
            return False
        return windows[0].get(WINDOW_OWNER_PID) == windows[1].get(WINDOW_OWNER_PID)

    def cursor_pos(self):
        """Current mouse cursor position in screen points."""
        location = self.quartz.CGEventGetLocation(self.quartz.CGEventCreate(None))
        return round(location.x), round(location.y)

    def _post_mouse(self, mouse_type, x, y):
        """Post one left-button mouse event at a screen point."""
        quartz = self.quartz
        point = quartz.CGPoint(float(x), float(y))
        event = quartz.CGEventCreateMouseEvent(None, mouse_type, point, quartz.kCGMouseButtonLeft)
        self._post(event, "mouse")

    def click(self, x, y):
        """Click the screen at the given coordinates."""
        self._post_mouse(self.quartz.kCGEventMouseMoved, x, y)
        time.sleep(CLICK_SETTLE_DELAY)
        self._post_mouse(self.quartz.kCGEventLeftMouseDown, x, y)
        try:
            time.sleep(CLICK_HOLD_DELAY)
        finally:
            self._post_mouse(self.quartz.kCGEventLeftMouseUp, x, y)
