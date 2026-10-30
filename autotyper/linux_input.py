"""Keyboard and mouse input for Linux: X11 through the XTEST extension.

Everything X11-specific lives here. The pure helpers are module-level
functions so they can be tested without a display; the X server is only
contacted when a :class:`LinuxInput` is created, never at import time.
"""

import logging
import time
from collections import namedtuple

from Xlib import XK, X, display, error
from Xlib.ext import xtest
from Xlib.protocol import event as xevent

from .errors import InputBackendError
from .keys import KEY_ESCAPE, KEY_F9, KEY_LEFT_BUTTON

logger = logging.getLogger(__name__)

KEYSYM_UNICODE_FLAG = 0x01000000
NO_SYMBOL = 0
ASCII_FIRST = 0x20
ASCII_LAST = 0x7E
BITS_PER_BYTE = 8
LEFT_BUTTON = 1
SOURCE_INDICATION_PAGER = 2
CLIENT_MESSAGE_FORMAT = 32
UNUSED_MESSAGE_DATA = 0
CLICK_SETTLE_DELAY = 0.05
CLICK_HOLD_DELAY = 0.03
KEYMAP_SETTLE_DELAY = 0.01
# Clients re-read the keymap lazily, after the key event arrives; restoring it at once
# makes them see an empty keycode and drop the character (GTK lost about 1 in 10).
UNICODE_HOLD_DELAY = 0.05
CLIENT_SEARCH_DEPTH = 3
XTEST_EXTENSION = "XTEST"
ACTIVATION_MASK = X.SubstructureRedirectMask | X.SubstructureNotifyMask

# Keymap columns: 0 is the plain symbol, 1 is the symbol with Shift held.
CHAR_TABLE_COLUMNS = ((0, False), (1, True))
CONTROL_CHARS = {"\n": (XK.XK_Return, "Return"), "\t": (XK.XK_Tab, "Tab")}
KEY_KEYSYMS = {KEY_ESCAPE: (XK.XK_Escape, "Escape"), KEY_F9: (XK.XK_F9, "F9")}

NO_DISPLAY_MESSAGE = (
    "AutoTyper could not connect to an X11 display. Start it from an X11 desktop session "
    "(on Wayland, run it through XWayland) and make sure DISPLAY is set."
)
NO_XTEST_MESSAGE = "The X server does not offer the XTEST extension, so AutoTyper cannot type."

KeyStroke = namedtuple("KeyStroke", "keycode shift")


class LinuxInputError(InputBackendError):
    """The X11 backend cannot start or cannot send input."""


def unicode_keysym(char):
    """X11 keysym that stands for any Unicode character."""
    return KEYSYM_UNICODE_FLAG | ord(char)


def keymap_bit_set(keymap, keycode):
    """True if ``keycode`` is down in a 32-byte ``query_keymap`` vector."""
    byte = keymap[keycode // BITS_PER_BYTE]
    return bool(byte & (1 << (keycode % BITS_PER_BYTE)))


def build_char_table(mapping, min_keycode):
    """Map each printable ASCII character to the key stroke that types it.

    ``mapping`` is the server's keyboard mapping, one row of keysyms per
    keycode starting at ``min_keycode``. Plain keys win over shifted ones and
    lower keycodes win over higher ones.
    """
    table = {}
    for column, needs_shift in CHAR_TABLE_COLUMNS:
        for offset, keysyms in enumerate(mapping):
            keysym = keysyms[column] if len(keysyms) > column else NO_SYMBOL
            if ASCII_FIRST <= keysym <= ASCII_LAST:
                table.setdefault(chr(keysym), KeyStroke(min_keycode + offset, needs_shift))
    return table


def find_spare_keycode(mapping, min_keycode, max_keycode):
    """Highest keycode below ``max_keycode`` that has no keysyms assigned."""
    for keycode in range(max_keycode - 1, min_keycode - 1, -1):
        if not any(mapping[keycode - min_keycode]):
            return keycode
    raise LinuxInputError("No free keycode is available for typing special characters.")


def climb_to_top_level(window, root_id):
    """Follow parent links from ``window`` up to the child of the root window."""
    while True:
        parent = window.query_tree().parent
        if not parent or parent.id == root_id:
            return window
        window = parent


def _has_property(window, atom):
    """True if the window carries the given property."""
    try:
        return window.get_full_property(atom, X.AnyPropertyType) is not None
    except error.XError as exc:
        logger.debug("Could not read a window property: %s", exc)
        return False


def _child_windows(window):
    """Children of a window, or none if it has vanished."""
    try:
        return window.query_tree().children
    except error.XError as exc:
        logger.debug("Could not list child windows: %s", exc)
        return []


def _search_for_property(window, atom, depth):
    """Depth-limited search below ``window`` for a window carrying ``atom``."""
    if depth <= 0:
        return None
    for child in _child_windows(window):
        if _has_property(child, atom):
            return child
        found = _search_for_property(child, atom, depth - 1)
        if found is not None:
            return found
    return None


def find_client_window(window, wm_state_atom, depth=CLIENT_SEARCH_DEPTH):
    """The application window inside a window-manager frame.

    Reparenting window managers wrap each application window in a frame that
    has no title. The real window is the one that carries ``WM_STATE``; when
    none is found (no window manager) the window itself is returned.
    """
    if _has_property(window, wm_state_atom):
        return window
    found = _search_for_property(window, wm_state_atom, depth)
    return window if found is None else found


def _decode_text(value):
    """Decode a window-name property value to text."""
    if isinstance(value, str):
        return value
    return bytes(value).decode("utf-8", errors="replace")


def read_window_title(x_display, handle):
    """Title of a window: ``_NET_WM_NAME``, else ``WM_NAME``, else ``""``."""
    if not handle:
        return ""
    window = x_display.create_resource_object("window", handle)
    try:
        net_name = window.get_full_property(
            x_display.intern_atom("_NET_WM_NAME"), x_display.intern_atom("UTF8_STRING")
        )
        if net_name is not None and len(net_name.value):
            return _decode_text(net_name.value)
        legacy_name = window.get_wm_name()
    except error.XError as exc:
        logger.debug("Could not read the title of window %s: %s", handle, exc)
        return ""
    return _decode_text(legacy_name) if legacy_name else ""


def _open_display():
    """Connect to the X server, translating failures into a readable error."""
    try:
        return display.Display()
    except (error.DisplayError, OSError) as exc:
        raise LinuxInputError(NO_DISPLAY_MESSAGE) from exc


class LinuxInput:
    """Sends real keystrokes and mouse clicks to an X11 desktop."""

    def __init__(self, x_display=None):
        self.display = x_display or _open_display()
        if not self.display.has_extension(XTEST_EXTENSION):
            raise LinuxInputError(NO_XTEST_MESSAGE)
        self.root = self.display.screen().root
        info = self.display.display.info
        self.min_keycode = info.min_keycode
        self.max_keycode = info.max_keycode
        self.char_table = build_char_table(self._read_mapping(), self.min_keycode)

    def close(self):
        """Disconnect from the X server."""
        self.display.close()

    def _read_mapping(self):
        """Current keyboard mapping, one row of keysyms per keycode."""
        count = self.max_keycode - self.min_keycode + 1
        return self.display.get_keyboard_mapping(self.min_keycode, count)

    def _keycode_for(self, keysym, label):
        """Keycode that produces ``keysym``; raises if the keyboard lacks it."""
        keycode = self.display.keysym_to_keycode(keysym)
        if not keycode:
            raise LinuxInputError(f"This keyboard layout has no {label} key.")
        return keycode

    def _fake_key(self, event_type, keycode):
        """Inject one key press or release."""
        xtest.fake_input(self.display, event_type, keycode)

    def _tap(self, keycode, hold_shift=False):
        """Press and release a key, optionally with Shift held."""
        shift = self._keycode_for(XK.XK_Shift_L, "Shift") if hold_shift else None
        if shift:
            self._fake_key(X.KeyPress, shift)
        try:
            self._fake_key(X.KeyPress, keycode)
            self._fake_key(X.KeyRelease, keycode)
        finally:
            if shift:
                self._fake_key(X.KeyRelease, shift)
            self.display.sync()

    def _discard_pending_events(self):
        """Drop queued server events; this connection never needs them."""
        while self.display.pending_events():
            self.display.next_event()

    def _type_unicode(self, char):
        """Type any character by temporarily binding it to a spare keycode."""
        spare = find_spare_keycode(self._read_mapping(), self.min_keycode, self.max_keycode)
        self.display.change_keyboard_mapping(spare, [(unicode_keysym(char),)])
        try:
            self.display.sync()
            time.sleep(KEYMAP_SETTLE_DELAY)
            self._tap(spare)
            time.sleep(UNICODE_HOLD_DELAY)
        finally:
            self.display.change_keyboard_mapping(spare, [(NO_SYMBOL,)])
            self.display.sync()
            self._discard_pending_events()

    def type_char(self, ch):
        """Type one character, including accents, CJK and emoji."""
        if ch == "\r":
            return
        if ch in CONTROL_CHARS:
            self._tap(self._keycode_for(*CONTROL_CHARS[ch]))
            return
        stroke = self.char_table.get(ch)
        if stroke is None:
            self._type_unicode(ch)
            return
        self._tap(stroke.keycode, hold_shift=self._shift_for(ch, stroke))

    def _caps_lock_on(self):
        """True while the Caps Lock modifier is active."""
        return bool(self.root.query_pointer().mask & X.LockMask)

    def _shift_for(self, ch, stroke):
        """Whether Shift must be held to type ``ch``; Caps Lock inverts letters."""
        if ch.isalpha() and self._caps_lock_on():
            return not stroke.shift
        return stroke.shift

    def key_down(self, key):
        """True while the named key (see ``keys.py``) is physically held."""
        if key == KEY_LEFT_BUTTON:
            return bool(self.root.query_pointer().mask & X.Button1Mask)
        if key not in KEY_KEYSYMS:
            raise ValueError(f"Unknown key: {key!r}")
        keycode = self._keycode_for(*KEY_KEYSYMS[key])
        return keymap_bit_set(self.display.query_keymap(), keycode)

    def cursor_pos(self):
        """Current mouse pointer position in screen pixels."""
        pointer = self.root.query_pointer()
        return pointer.root_x, pointer.root_y

    def _as_window(self, value):
        """Accept either a window object or a bare window id."""
        if isinstance(value, int):
            return self.display.create_resource_object("window", value)
        return value

    def root_window_at(self, x, y):
        """Id of the application window under the given screen coordinates."""
        child = self.root.translate_coords(self.root, int(x), int(y)).child
        if not child:
            return None
        top_level = climb_to_top_level(self._as_window(child), self.root.id)
        wm_state = self.display.intern_atom("WM_STATE")
        return find_client_window(top_level, wm_state).id

    def window_title(self, handle):
        """Title bar text of a window handle; empty if it cannot be read."""
        return read_window_title(self.display, handle)

    def _active_window_id(self):
        """Window id from ``_NET_ACTIVE_WINDOW``, or None without a window manager."""
        atom = self.display.intern_atom("_NET_ACTIVE_WINDOW")
        try:
            active = self.root.get_full_property(atom, X.AnyPropertyType)
        except error.XError as exc:
            logger.debug("Could not read _NET_ACTIVE_WINDOW: %s", exc)
            return None
        if active is None or not len(active.value):
            return None
        return int(active.value[0]) or None

    def _focused_window_id(self):
        """Window id that holds the X input focus, or None."""
        focus = self.display.get_input_focus().focus
        window_id = getattr(focus, "id", focus)
        if window_id in (X.NONE, X.PointerRoot):
            return None
        return window_id

    def foreground(self):
        """Handle of the window that currently has keyboard focus."""
        return self._active_window_id() or self._focused_window_id()

    @staticmethod
    def _log_x_error(failure, _request=None):
        """Error handler for requests without a reply; True marks it as handled."""
        logger.debug("Ignored X error: %s", failure)
        return True

    def _raise_window(self, window):
        """Stack the window on top of its siblings."""
        raiser = getattr(window, "raise_", None)
        if raiser:
            raiser(onerror=self._log_x_error)
        else:
            window.configure(stack_mode=X.Above, onerror=self._log_x_error)

    def _request_activation(self, window):
        """Ask an EWMH window manager to activate the window, as a pager would."""
        atom = self.display.intern_atom("_NET_ACTIVE_WINDOW")
        data = [SOURCE_INDICATION_PAGER, X.CurrentTime] + [UNUSED_MESSAGE_DATA] * 3
        message = xevent.ClientMessage(
            window=window, client_type=atom, data=(CLIENT_MESSAGE_FORMAT, data)
        )
        self.root.send_event(message, event_mask=ACTIVATION_MASK, onerror=self._log_x_error)

    def focus(self, handle):
        """Bring a window back to the foreground."""
        if not handle:
            return
        window = self.display.create_resource_object("window", handle)
        self._raise_window(window)
        self._request_activation(window)
        self.display.set_input_focus(
            window, X.RevertToParent, X.CurrentTime, onerror=self._log_x_error
        )
        try:
            self.display.sync()
        except error.XError as exc:
            logger.debug("X error while focusing window %s: %s", handle, exc)

    def click(self, x, y):
        """Click the screen at the given coordinates."""
        xtest.fake_input(self.display, X.MotionNotify, x=int(x), y=int(y))
        self.display.sync()
        time.sleep(CLICK_SETTLE_DELAY)
        xtest.fake_input(self.display, X.ButtonPress, LEFT_BUTTON)
        try:
            self.display.sync()  # without it the press and release leave in one batch
            time.sleep(CLICK_HOLD_DELAY)
        finally:
            xtest.fake_input(self.display, X.ButtonRelease, LEFT_BUTTON)
            self.display.sync()
