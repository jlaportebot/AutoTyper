"""Tests for the X11/XTEST input backend.

The pure helpers and the backend logic run against a fake display, so they
need no X server. The integration class talks to a real server and is
skipped when ``DISPLAY`` is not set (on CI it runs under ``xvfb-run``).
"""

import os
import shutil
import subprocess
import sys
import time
import types
import unittest
from unittest import mock

try:
    import Xlib  # noqa: F401  (only checks that python-xlib is installed)
except ImportError as exc:
    raise unittest.SkipTest(f"python-xlib is not installed: {exc}") from exc

from Xlib import XK, X, display, error
from Xlib.ext import xtest

from autotyper import linux_input
from autotyper.errors import InputBackendError
from autotyper.keys import KEY_ESCAPE, KEY_F9, KEY_LEFT_BUTTON
from autotyper.linux_input import (
    KeyStroke,
    LinuxInput,
    LinuxInputError,
    build_char_table,
    climb_to_top_level,
    find_client_window,
    find_spare_keycode,
    keymap_bit_set,
    read_window_title,
    unicode_keysym,
)

HAS_DISPLAY = bool(os.environ.get("DISPLAY"))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MIN_UNICODE_HOLD = 0.05
OPENBOX = shutil.which("openbox")
WM_START_TIMEOUT = 15.0
WM_POLL_INTERVAL = 0.05
INSIDE_OFFSET = 20
STALE_ROOT_PROPERTIES = ("_NET_SUPPORTING_WM_CHECK", "_NET_ACTIVE_WINDOW")
MIN_KEYCODE = 8
MAX_KEYCODE = 255
KEYSYMS_PER_KEYCODE = 4
KEYCODE_RETURN = 36
KEYCODE_TAB = 23
KEYCODE_ESCAPE = 9
KEYCODE_F9 = 75
KEYCODE_SHIFT = 50
KEYCODE_A = 38
KEYCODE_SPACE = 65
KEYCODE_ONE = 10
SPARE_KEYCODE = MAX_KEYCODE - 1
ROOT_ID = 1
ACTIVE_WINDOW_ID = 4242
FOCUSED_WINDOW_ID = 777
SOURCE_PAGER = 2


def make_mapping():
    """A small keyboard mapping covering the keys the tests use."""
    count = MAX_KEYCODE - MIN_KEYCODE + 1
    mapping = [[0] * KEYSYMS_PER_KEYCODE for _ in range(count)]
    entries = {
        KEYCODE_ESCAPE: [XK.XK_Escape],
        KEYCODE_TAB: [XK.XK_Tab],
        KEYCODE_SHIFT: [XK.XK_Shift_L],
        KEYCODE_RETURN: [XK.XK_Return],
        KEYCODE_F9: [XK.XK_F9],
        KEYCODE_A: [ord("a"), ord("A")],
        KEYCODE_SPACE: [ord(" ")],
        KEYCODE_ONE: [ord("1"), ord("!")],
    }
    for keycode, keysyms in entries.items():
        mapping[keycode - MIN_KEYCODE][: len(keysyms)] = keysyms
    return mapping


class FakeXError(error.XError):
    """An X protocol error that can be raised without a server."""

    def __init__(self):
        Exception.__init__(self, "fake X error")


class FakeProperty:
    def __init__(self, value):
        self.value = value


class FakeWindow:
    """Just enough of an Xlib window for the backend."""

    def __init__(self, window_id, parent=None, children=(), properties=None, wm_name=None,
                 failing=False):
        self.id = window_id
        self.parent = parent
        self.children = list(children)
        self.properties = properties or {}
        self.wm_name = wm_name
        self.failing = failing
        self.calls = []
        self.messages = []

    def __window__(self):
        return self.id

    def query_tree(self):
        return types.SimpleNamespace(parent=self.parent or 0, children=self.children)

    def get_full_property(self, atom, _property_type, *_args):
        if self.failing:
            raise FakeXError()
        value = self.properties.get(atom)
        return None if value is None else FakeProperty(value)

    def get_wm_name(self):
        if self.failing:
            raise FakeXError()
        return self.wm_name

    def raise_(self, onerror=None):
        self.calls.append("raise")

    def send_event(self, event, event_mask=0, onerror=None):
        self.messages.append((event, event_mask))

    def translate_coords(self, _destination, _x, _y):
        return types.SimpleNamespace(child=0)

    def query_pointer(self):
        return types.SimpleNamespace(mask=0, root_x=0, root_y=0, child=0)


class FakeDisplay:
    """Records the requests the backend sends and answers from fixtures."""

    ATOMS = ("_NET_ACTIVE_WINDOW", "_NET_WM_NAME", "UTF8_STRING", "WM_STATE")

    def __init__(self, mapping=None):
        self.display = types.SimpleNamespace(
            info=types.SimpleNamespace(min_keycode=MIN_KEYCODE, max_keycode=MAX_KEYCODE)
        )
        self.mapping = mapping if mapping is not None else make_mapping()
        self.keymap = [0] * 32
        self.root = FakeWindow(ROOT_ID)
        self.windows = {ROOT_ID: self.root}
        self.focus = FOCUSED_WINDOW_ID
        self.remaps = []
        self.focus_requests = []
        self.sync_error = None
        self.closed = False
        self.extensions = {"XTEST"}
        self.keysyms = {
            XK.XK_Return: KEYCODE_RETURN, XK.XK_Tab: KEYCODE_TAB,
            XK.XK_Escape: KEYCODE_ESCAPE, XK.XK_F9: KEYCODE_F9, XK.XK_Shift_L: KEYCODE_SHIFT,
        }

    def has_extension(self, name):
        return name in self.extensions

    def screen(self):
        return types.SimpleNamespace(root=self.root)

    def get_keyboard_mapping(self, _first, _count):
        return self.mapping

    def keysym_to_keycode(self, keysym):
        return self.keysyms.get(keysym, 0)

    def change_keyboard_mapping(self, first_keycode, keysyms, onerror=None):
        self.remaps.append((first_keycode, list(keysyms)))

    def query_keymap(self):
        return self.keymap

    def intern_atom(self, name):
        return 100 + self.ATOMS.index(name)

    def get_input_focus(self):
        return types.SimpleNamespace(focus=self.focus)

    def create_resource_object(self, _kind, window_id):
        return self.windows.setdefault(window_id, FakeWindow(window_id))

    def set_input_focus(self, window, revert_to, time, onerror=None):
        self.focus_requests.append(window.id)

    def sync(self):
        if self.sync_error:
            raise self.sync_error

    def flush(self):
        return None

    def pending_events(self):
        return 0

    def close(self):
        self.closed = True

    def press_keycode(self, keycode):
        self.keymap[keycode // 8] |= 1 << (keycode % 8)


class FakeXtest:
    """Stands in for ``Xlib.ext.xtest`` and records injected events."""

    def __init__(self):
        self.events = []
        self.failure = None

    def fake_input(self, _display, event_type, detail=0, time=0, root=0, x=0, y=0):
        if self.failure:
            raise self.failure
        self.events.append((event_type, detail) if not x and not y else (event_type, x, y))


def make_backend(fake_display=None):
    """A LinuxInput wired to a fake display and a recording XTEST."""
    fake_display = fake_display or FakeDisplay()
    backend = LinuxInput(x_display=fake_display)
    return backend, fake_display


class PureHelpers(unittest.TestCase):
    def test_unicode_keysym_sets_the_unicode_flag(self):
        self.assertEqual(unicode_keysym("é"), 0x010000E9)
        self.assertEqual(unicode_keysym("中"), 0x01004E2D)

    def test_unicode_keysym_covers_characters_outside_the_bmp(self):
        self.assertEqual(unicode_keysym("😀"), 0x0101F600)

    def test_keymap_bit_set_finds_a_pressed_key(self):
        keymap = [0] * 32
        keymap[KEYCODE_F9 // 8] = 1 << (KEYCODE_F9 % 8)
        self.assertTrue(keymap_bit_set(keymap, KEYCODE_F9))

    def test_keymap_bit_set_ignores_neighbouring_keys(self):
        keymap = [0] * 32
        keymap[KEYCODE_F9 // 8] = 1 << (KEYCODE_F9 % 8)
        self.assertFalse(keymap_bit_set(keymap, KEYCODE_F9 + 1))
        self.assertFalse(keymap_bit_set(keymap, KEYCODE_F9 - 1))

    def test_keymap_bit_set_accepts_bytes(self):
        keymap = bytes([0] * 9 + [0b00001000] + [0] * 22)
        self.assertTrue(keymap_bit_set(keymap, 75))

    def test_char_table_maps_lowercase_without_shift(self):
        table = build_char_table(make_mapping(), MIN_KEYCODE)
        self.assertEqual(table["a"], KeyStroke(KEYCODE_A, False))

    def test_char_table_maps_uppercase_with_shift(self):
        table = build_char_table(make_mapping(), MIN_KEYCODE)
        self.assertEqual(table["A"], KeyStroke(KEYCODE_A, True))

    def test_char_table_maps_shifted_symbols_with_shift(self):
        table = build_char_table(make_mapping(), MIN_KEYCODE)
        self.assertEqual(table["1"], KeyStroke(KEYCODE_ONE, False))
        self.assertEqual(table["!"], KeyStroke(KEYCODE_ONE, True))

    def test_char_table_maps_space(self):
        table = build_char_table(make_mapping(), MIN_KEYCODE)
        self.assertEqual(table[" "], KeyStroke(KEYCODE_SPACE, False))

    def test_char_table_prefers_the_unshifted_key_when_a_symbol_appears_twice(self):
        mapping = make_mapping()
        mapping[200 - MIN_KEYCODE][:2] = [ord("!"), 0]
        table = build_char_table(mapping, MIN_KEYCODE)
        self.assertEqual(table["!"], KeyStroke(200, False))

    def test_char_table_skips_non_ascii_and_function_keysyms(self):
        table = build_char_table(make_mapping(), MIN_KEYCODE)
        self.assertNotIn("é", table)
        self.assertEqual({char for char in table if not char.isprintable()}, set())
        self.assertNotIn(chr(XK.XK_Return & 0x7F), table)

    def test_spare_keycode_is_the_highest_free_one_below_the_maximum(self):
        self.assertEqual(find_spare_keycode(make_mapping(), MIN_KEYCODE, MAX_KEYCODE),
                         SPARE_KEYCODE)

    def test_spare_keycode_skips_keycodes_that_are_in_use(self):
        mapping = make_mapping()
        mapping[SPARE_KEYCODE - MIN_KEYCODE][0] = ord("x")
        self.assertEqual(find_spare_keycode(mapping, MIN_KEYCODE, MAX_KEYCODE),
                         SPARE_KEYCODE - 1)

    def test_spare_keycode_raises_when_every_keycode_is_mapped(self):
        mapping = [[ord("x")] * KEYSYMS_PER_KEYCODE for _ in make_mapping()]
        with self.assertRaisesRegex(LinuxInputError, "free keycode"):
            find_spare_keycode(mapping, MIN_KEYCODE, MAX_KEYCODE)

    def test_climb_stops_at_the_child_of_the_root(self):
        top = FakeWindow(10, parent=types.SimpleNamespace(id=ROOT_ID))
        middle = FakeWindow(11, parent=top)
        leaf = FakeWindow(12, parent=middle)
        self.assertIs(climb_to_top_level(leaf, ROOT_ID), top)

    def test_climb_returns_the_window_when_it_is_already_top_level(self):
        top = FakeWindow(10, parent=types.SimpleNamespace(id=ROOT_ID))
        self.assertIs(climb_to_top_level(top, ROOT_ID), top)

    def test_climb_stops_when_a_window_has_no_parent(self):
        orphan = FakeWindow(10)
        self.assertIs(climb_to_top_level(orphan, ROOT_ID), orphan)

    def test_client_window_is_the_frame_itself_when_it_carries_wm_state(self):
        frame = FakeWindow(10, properties={103: [1, 0]})
        self.assertIs(find_client_window(frame, 103), frame)

    def test_client_window_is_found_inside_a_window_manager_frame(self):
        client = FakeWindow(12, properties={103: [1, 0]})
        decoration = FakeWindow(11, children=[client])
        frame = FakeWindow(10, children=[decoration])
        self.assertIs(find_client_window(frame, 103), client)

    def test_client_window_falls_back_to_the_frame_without_wm_state(self):
        frame = FakeWindow(10, children=[FakeWindow(11)])
        self.assertIs(find_client_window(frame, 103), frame)


class WindowTitles(unittest.TestCase):
    def setUp(self):
        self.display = FakeDisplay()

    def title_of(self, handle):
        return read_window_title(self.display, handle)

    def test_returns_empty_string_for_none(self):
        self.assertEqual(self.title_of(None), "")

    def test_returns_empty_string_for_zero(self):
        self.assertEqual(self.title_of(0), "")

    def test_prefers_the_utf8_net_wm_name(self):
        net_wm_name = self.display.intern_atom("_NET_WM_NAME")
        window = FakeWindow(5, properties={net_wm_name: "Tëst ✓".encode()}, wm_name="legacy")
        self.display.windows[5] = window
        self.assertEqual(self.title_of(5), "Tëst ✓")

    def test_falls_back_to_the_legacy_wm_name(self):
        self.display.windows[5] = FakeWindow(5, wm_name="legacy")
        self.assertEqual(self.title_of(5), "legacy")

    def test_decodes_a_bytes_legacy_name(self):
        self.display.windows[5] = FakeWindow(5, wm_name=b"legacy")
        self.assertEqual(self.title_of(5), "legacy")

    def test_returns_empty_string_when_the_window_has_no_name(self):
        self.display.windows[5] = FakeWindow(5)
        self.assertEqual(self.title_of(5), "")

    def test_returns_empty_string_for_a_window_that_no_longer_exists(self):
        self.display.windows[5] = FakeWindow(5, failing=True)
        self.assertEqual(self.title_of(5), "")

    def test_replaces_invalid_utf8_instead_of_raising(self):
        net_wm_name = self.display.intern_atom("_NET_WM_NAME")
        self.display.windows[5] = FakeWindow(5, properties={net_wm_name: b"ab\xff"})
        self.assertEqual(self.title_of(5), "ab�")


class StartUp(unittest.TestCase):
    def test_reports_a_missing_display_in_plain_words(self):
        failure = error.DisplayConnectionError(":99", "refused")
        with mock.patch.object(linux_input.display, "Display", side_effect=failure), \
                self.assertRaisesRegex(LinuxInputError, "X11 display"):
            LinuxInput()

    def test_reports_an_invalid_display_name(self):
        failure = error.DisplayNameError("bogus")
        with mock.patch.object(linux_input.display, "Display", side_effect=failure), \
                self.assertRaisesRegex(LinuxInputError, "X11 display"):
            LinuxInput()

    def test_start_up_errors_are_input_backend_errors(self):
        self.assertTrue(issubclass(LinuxInputError, InputBackendError))

    def test_importing_the_module_does_not_need_a_display(self):
        env = {key: value for key, value in os.environ.items() if key != "DISPLAY"}
        env["PYTHONPATH"] = REPO_ROOT
        result = subprocess.run(
            [sys.executable, "-c", "import autotyper.linux_input"],
            env=env, cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reports_a_server_without_the_xtest_extension(self):
        fake = FakeDisplay()
        fake.extensions.clear()
        with self.assertRaisesRegex(LinuxInputError, "XTEST"):
            make_backend(fake)

    def test_close_closes_the_display(self):
        backend, fake = make_backend()
        backend.close()
        self.assertTrue(fake.closed)


class TypeChar(unittest.TestCase):
    def setUp(self):
        self.xtest = FakeXtest()
        patcher = mock.patch.object(linux_input, "xtest", self.xtest)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleeper = mock.patch.object(linux_input.time, "sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)
        self.backend, self.display = make_backend()

    def press_release(self, keycode):
        return [(X.KeyPress, keycode), (X.KeyRelease, keycode)]

    def test_carriage_return_is_ignored(self):
        self.backend.type_char("\r")
        self.assertEqual(self.xtest.events, [])

    def test_newline_presses_return(self):
        self.backend.type_char("\n")
        self.assertEqual(self.xtest.events, self.press_release(KEYCODE_RETURN))

    def test_tab_presses_tab(self):
        self.backend.type_char("\t")
        self.assertEqual(self.xtest.events, self.press_release(KEYCODE_TAB))

    def test_lowercase_letter_is_typed_without_shift(self):
        self.backend.type_char("a")
        self.assertEqual(self.xtest.events, self.press_release(KEYCODE_A))

    def test_uppercase_letter_holds_shift(self):
        self.backend.type_char("A")
        expected = [(X.KeyPress, KEYCODE_SHIFT), *self.press_release(KEYCODE_A),
                    (X.KeyRelease, KEYCODE_SHIFT)]
        self.assertEqual(self.xtest.events, expected)

    def test_shifted_symbol_holds_shift(self):
        self.backend.type_char("!")
        self.assertEqual(self.xtest.events[0], (X.KeyPress, KEYCODE_SHIFT))
        self.assertEqual(self.xtest.events[-1], (X.KeyRelease, KEYCODE_SHIFT))

    def set_caps_lock(self, on):
        self.display.root.query_pointer = lambda: types.SimpleNamespace(
            mask=X.LockMask if on else 0
        )

    def test_caps_lock_makes_a_lowercase_letter_hold_shift(self):
        self.set_caps_lock(True)
        self.backend.type_char("a")
        expected = [(X.KeyPress, KEYCODE_SHIFT), *self.press_release(KEYCODE_A),
                    (X.KeyRelease, KEYCODE_SHIFT)]
        self.assertEqual(self.xtest.events, expected)

    def test_caps_lock_lets_an_uppercase_letter_go_without_shift(self):
        self.set_caps_lock(True)
        self.backend.type_char("A")
        self.assertEqual(self.xtest.events, self.press_release(KEYCODE_A))

    def test_caps_lock_does_not_change_digits_or_symbols(self):
        self.set_caps_lock(True)
        self.backend.type_char("1")
        self.assertEqual(self.xtest.events, self.press_release(KEYCODE_ONE))
        self.xtest.events.clear()
        self.backend.type_char("!")
        self.assertEqual(self.xtest.events[0], (X.KeyPress, KEYCODE_SHIFT))

    def test_accented_letter_uses_a_remapped_spare_keycode(self):
        self.backend.type_char("é")
        self.assertEqual(self.xtest.events, self.press_release(SPARE_KEYCODE))
        self.assertEqual(self.display.remaps[0], (SPARE_KEYCODE, [(0x010000E9,)]))

    def test_emoji_uses_the_unicode_keysym(self):
        self.backend.type_char("😀")
        self.assertEqual(self.display.remaps[0], (SPARE_KEYCODE, [(0x0101F600,)]))

    def test_keymap_is_restored_after_a_unicode_character(self):
        self.backend.type_char("中")
        self.assertEqual(self.display.remaps[-1], (SPARE_KEYCODE, [(0,)]))

    def record_state_at_each_sleep(self):
        """Replace time.sleep with a recorder of ``(seconds, key events, keymap changes)``."""
        sleeps = []

        def record(seconds):
            sleeps.append((seconds, len(self.xtest.events), len(self.display.remaps)))

        linux_input.time.sleep.side_effect = record
        return sleeps

    def test_unicode_keymap_stays_bound_after_the_key_so_clients_can_read_it(self):
        sleeps = self.record_state_at_each_sleep()
        self.backend.type_char("é")
        key_sent, bound = len(self.press_release(SPARE_KEYCODE)), 1
        holds = [seconds for seconds, events, remaps in sleeps
                 if (events, remaps) == (key_sent, bound)]
        self.assertTrue(holds and max(holds) >= MIN_UNICODE_HOLD, sleeps)

    def test_plain_ascii_never_waits_for_clients(self):
        sleeps = self.record_state_at_each_sleep()
        for char in "aA\n\t":
            self.backend.type_char(char)
        self.assertEqual(sleeps, [])

    def test_keymap_is_restored_when_sending_the_key_fails(self):
        self.xtest.failure = OSError("server went away")
        with self.assertRaises(OSError):
            self.backend.type_char("é")
        self.assertEqual(self.display.remaps[-1], (SPARE_KEYCODE, [(0,)]))

    def test_shift_is_released_when_sending_the_key_fails(self):
        calls = []
        original = self.xtest.fake_input

        def failing_on_letter(display_, event_type, detail=0, **kwargs):
            calls.append((event_type, detail))
            if detail == KEYCODE_A:
                raise OSError("boom")
            return original(display_, event_type, detail, **kwargs)

        self.xtest.fake_input = failing_on_letter
        with self.assertRaises(OSError):
            self.backend.type_char("A")
        self.assertEqual(calls[-1], (X.KeyRelease, KEYCODE_SHIFT))

    def test_unicode_without_a_free_keycode_raises_a_clear_error(self):
        full = [[ord("x")] * KEYSYMS_PER_KEYCODE for _ in make_mapping()]
        backend, _ = make_backend(FakeDisplay(mapping=full))
        with self.assertRaisesRegex(LinuxInputError, "free keycode"):
            backend.type_char("é")

    def test_missing_return_key_raises_a_clear_error(self):
        fake = FakeDisplay()
        fake.keysyms.pop(XK.XK_Return)
        backend, _ = make_backend(fake)
        with self.assertRaisesRegex(LinuxInputError, "Return"):
            backend.type_char("\n")


class KeyState(unittest.TestCase):
    def setUp(self):
        self.backend, self.display = make_backend()

    def test_escape_is_reported_while_held(self):
        self.display.press_keycode(KEYCODE_ESCAPE)
        self.assertTrue(self.backend.key_down(KEY_ESCAPE))

    def test_f9_is_reported_while_held(self):
        self.display.press_keycode(KEYCODE_F9)
        self.assertTrue(self.backend.key_down(KEY_F9))

    def test_keys_are_reported_released_by_default(self):
        self.assertFalse(self.backend.key_down(KEY_ESCAPE))
        self.assertFalse(self.backend.key_down(KEY_F9))

    def test_a_different_key_does_not_trigger_escape(self):
        self.display.press_keycode(KEYCODE_F9)
        self.assertFalse(self.backend.key_down(KEY_ESCAPE))

    def test_left_button_is_reported_from_the_pointer_mask(self):
        self.display.root.query_pointer = lambda: types.SimpleNamespace(mask=X.Button1Mask)
        self.assertTrue(self.backend.key_down(KEY_LEFT_BUTTON))

    def test_left_button_ignores_other_pointer_buttons(self):
        self.display.root.query_pointer = lambda: types.SimpleNamespace(mask=X.Button3Mask)
        self.assertFalse(self.backend.key_down(KEY_LEFT_BUTTON))

    def test_unknown_key_name_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "enter"):
            self.backend.key_down("enter")

    def test_legacy_integer_codes_are_rejected(self):
        with self.assertRaises(ValueError):
            self.backend.key_down(0x78)

    def test_missing_key_on_the_keyboard_raises_a_clear_error(self):
        fake = FakeDisplay()
        fake.keysyms.pop(XK.XK_F9)
        with self.assertRaisesRegex(LinuxInputError, "F9"):
            make_backend(fake)[0].key_down(KEY_F9)


class WindowQueries(unittest.TestCase):
    def setUp(self):
        self.backend, self.display = make_backend()
        self.active = self.display.intern_atom("_NET_ACTIVE_WINDOW")

    def test_foreground_prefers_the_ewmh_active_window(self):
        self.display.root.properties[self.active] = [ACTIVE_WINDOW_ID]
        self.assertEqual(self.backend.foreground(), ACTIVE_WINDOW_ID)

    def test_foreground_falls_back_to_the_input_focus_without_a_window_manager(self):
        self.assertEqual(self.backend.foreground(), FOCUSED_WINDOW_ID)

    def test_foreground_falls_back_when_the_active_window_is_none(self):
        self.display.root.properties[self.active] = [0]
        self.assertEqual(self.backend.foreground(), FOCUSED_WINDOW_ID)

    def test_foreground_reads_the_id_from_a_focus_window_object(self):
        self.display.focus = FakeWindow(FOCUSED_WINDOW_ID)
        self.assertEqual(self.backend.foreground(), FOCUSED_WINDOW_ID)

    def test_foreground_is_none_when_nothing_has_focus(self):
        self.display.focus = X.NONE
        self.assertIsNone(self.backend.foreground())

    def test_foreground_is_none_when_focus_follows_the_pointer(self):
        self.display.focus = X.PointerRoot
        self.assertIsNone(self.backend.foreground())

    def test_foreground_survives_a_protocol_error(self):
        self.display.root.failing = True
        self.assertEqual(self.backend.foreground(), FOCUSED_WINDOW_ID)

    def test_cursor_pos_reads_the_root_pointer(self):
        self.display.root.query_pointer = lambda: types.SimpleNamespace(root_x=120, root_y=240)
        self.assertEqual(self.backend.cursor_pos(), (120, 240))

    def test_window_title_is_empty_for_none(self):
        self.assertEqual(self.backend.window_title(None), "")

    def test_root_window_at_returns_the_top_level_window(self):
        top = FakeWindow(10, parent=self.display.root)
        leaf = FakeWindow(12, parent=FakeWindow(11, parent=top))
        self.display.root.translate_coords = lambda *_: types.SimpleNamespace(child=leaf)
        self.assertEqual(self.backend.root_window_at(5, 5), 10)

    def test_root_window_at_prefers_the_client_inside_a_wm_frame(self):
        wm_state = self.display.intern_atom("WM_STATE")
        client = FakeWindow(12, properties={wm_state: [1, 0]})
        frame = FakeWindow(10, parent=self.display.root, children=[client])
        self.display.root.translate_coords = lambda *_: types.SimpleNamespace(child=frame)
        self.assertEqual(self.backend.root_window_at(5, 5), 12)

    def test_root_window_at_is_none_over_the_bare_root(self):
        self.assertIsNone(self.backend.root_window_at(5, 5))


class FocusAndClick(unittest.TestCase):
    def setUp(self):
        self.xtest = FakeXtest()
        patcher = mock.patch.object(linux_input, "xtest", self.xtest)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleeper = mock.patch.object(linux_input.time, "sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)
        self.backend, self.display = make_backend()

    def test_focus_ignores_an_empty_handle(self):
        self.backend.focus(None)
        self.assertEqual(self.display.focus_requests, [])
        self.assertEqual(self.display.root.messages, [])

    def test_focus_raises_the_window_and_sets_input_focus(self):
        self.backend.focus(55)
        self.assertEqual(self.display.windows[55].calls, ["raise"])
        self.assertEqual(self.display.focus_requests, [55])

    def test_focus_asks_the_window_manager_as_a_pager(self):
        self.backend.focus(55)
        (event, mask), = self.display.root.messages
        self.assertEqual(event.client_type, self.display.intern_atom("_NET_ACTIVE_WINDOW"))
        self.assertEqual(event.data[0], 32)
        self.assertEqual(event.data[1][0], SOURCE_PAGER)
        self.assertTrue(mask & X.SubstructureRedirectMask)

    def test_focus_does_not_raise_when_the_server_reports_an_error(self):
        self.display.sync_error = FakeXError()
        self.backend.focus(55)

    def test_x_error_handler_reports_the_error_as_handled(self):
        self.assertTrue(LinuxInput._log_x_error(FakeXError(), None))

    def test_focus_falls_back_to_configure_when_raise_is_unavailable(self):
        window = FakeWindow(55)
        window.raise_ = None
        window.configure = lambda **kwargs: window.calls.append(kwargs["stack_mode"])
        self.display.windows[55] = window
        self.backend.focus(55)
        self.assertEqual(window.calls, [X.Above])

    def test_click_moves_then_presses_and_releases_button_one(self):
        self.backend.click(30, 40)
        self.assertEqual(self.xtest.events, [
            (X.MotionNotify, 30, 40), (X.ButtonPress, 1), (X.ButtonRelease, 1),
        ])

    def test_click_pauses_between_press_and_release(self):
        self.backend.click(30, 40)
        self.sleep.assert_called()

    def test_click_sends_the_press_to_the_server_before_holding_the_button(self):
        log = []
        record_event = self.xtest.fake_input

        def fake_input(display_, event_type, *args, **kwargs):
            log.append(("event", event_type))
            return record_event(display_, event_type, *args, **kwargs)

        self.xtest.fake_input = fake_input
        self.display.sync = lambda: log.append(("flush",))
        self.display.flush = lambda: log.append(("flush",))
        self.sleep.side_effect = lambda seconds: log.append(("sleep", seconds))
        self.backend.click(30, 40)
        press = log.index(("event", X.ButtonPress))
        hold = next(i for i in range(press, len(log)) if log[i][0] == "sleep")
        self.assertIn(("flush",), log[press:hold], log)

    def test_click_releases_the_button_if_it_is_interrupted_while_held(self):
        self.sleep.side_effect = [None, RuntimeError("interrupted")]
        with self.assertRaises(RuntimeError):
            self.backend.click(30, 40)
        self.assertEqual(self.xtest.events[-1], (X.ButtonRelease, 1))

    def test_click_propagates_xtest_failures(self):
        self.xtest.failure = OSError("server went away")
        with self.assertRaises(OSError):
            self.backend.click(30, 40)


@unittest.skipUnless(HAS_DISPLAY, "no X display available")
class XvfbIntegration(unittest.TestCase):
    """Drives the real backend against a real X server."""

    WINDOW_SIZE = (200, 100)
    EVENT_MASK = X.KeyPressMask | X.KeyReleaseMask | X.ButtonPressMask

    @classmethod
    def setUpClass(cls):
        # Xvfb resets when its last client leaves; one open connection avoids
        # racing the reset between tests.
        cls.keep_alive = display.Display()

    @classmethod
    def tearDownClass(cls):
        cls.keep_alive.close()

    def setUp(self):
        self.backend = LinuxInput()
        self.addCleanup(self.backend.close)
        self.observer = display.Display()
        self.addCleanup(self.observer.close)
        self.window = self.make_window(0, 0)
        self.focus_window(self.window)

    def make_window(self, x, y):
        screen = self.observer.screen()
        width, height = self.WINDOW_SIZE
        window = screen.root.create_window(
            x, y, width, height, 0, screen.root_depth, X.InputOutput, X.CopyFromParent,
            event_mask=self.EVENT_MASK,
        )
        window.map()
        self.observer.sync()
        self.addCleanup(self.destroy, window)
        return window

    def destroy(self, window):
        window.destroy(onerror=lambda *_: True)
        self.observer.sync()

    def focus_window(self, window):
        self.observer.set_input_focus(window, X.RevertToParent, X.CurrentTime)
        self.observer.sync()

    def drain_events(self):
        self.observer.sync()
        events = []
        while self.observer.pending_events():
            events.append(self.observer.next_event())
        return events

    def key_events(self):
        return [(ev.type, ev.detail, ev.state) for ev in self.drain_events()
                if ev.type in (X.KeyPress, X.KeyRelease)]

    def keycode(self, keysym):
        return self.observer.keysym_to_keycode(keysym)

    def test_lowercase_letter_arrives_as_an_unshifted_key(self):
        self.backend.type_char("a")
        expected_code = self.keycode(XK.XK_a)
        self.assertEqual([(t, d, s & X.ShiftMask) for t, d, s in self.key_events()],
                         [(X.KeyPress, expected_code, 0), (X.KeyRelease, expected_code, 0)])

    def test_uppercase_letter_arrives_with_shift_held(self):
        self.backend.type_char("A")
        letter = [(t, s & X.ShiftMask) for t, d, s in self.key_events()
                  if d == self.keycode(XK.XK_a)]
        self.assertEqual(letter, [(X.KeyPress, X.ShiftMask), (X.KeyRelease, X.ShiftMask)])

    def toggle_caps_lock(self):
        code = self.keycode(XK.XK_Caps_Lock)
        xtest.fake_input(self.observer, X.KeyPress, code)
        xtest.fake_input(self.observer, X.KeyRelease, code)
        self.observer.sync()

    def test_letters_keep_their_case_while_caps_lock_is_on(self):
        self.toggle_caps_lock()
        self.addCleanup(self.toggle_caps_lock)
        self.drain_events()
        self.backend.type_char("a")
        letter_state = [s for t, d, s in self.key_events()
                        if t == X.KeyPress and d == self.keycode(XK.XK_a)]
        self.assertEqual([bool(s & X.LockMask) for s in letter_state], [True])
        self.assertEqual([bool(s & X.ShiftMask) for s in letter_state], [True])

    def test_newline_arrives_as_return(self):
        self.backend.type_char("\n")
        codes = {d for _t, d, _s in self.key_events()}
        self.assertEqual(codes, {self.keycode(XK.XK_Return)})

    def test_unicode_character_arrives_on_a_spare_keycode_and_keymap_is_restored(self):
        count = MAX_KEYCODE - MIN_KEYCODE + 1
        before = [list(row) for row in self.observer.get_keyboard_mapping(MIN_KEYCODE, count)]
        self.backend.type_char("é")
        codes = {d for _t, d, _s in self.key_events()}
        after = [list(row) for row in self.observer.get_keyboard_mapping(MIN_KEYCODE, count)]
        self.assertEqual(len(codes), 1)
        self.assertEqual(before[codes.pop() - MIN_KEYCODE], [0] * len(before[0]))
        self.assertEqual(after, before)

    def test_plain_ascii_never_touches_the_keymap(self):
        with mock.patch.object(self.backend.display, "change_keyboard_mapping") as remap:
            for char in "Hello, World 123!":
                self.backend.type_char(char)
        remap.assert_not_called()

    def test_key_down_follows_a_physical_f9_press(self):
        code = self.keycode(XK.XK_F9)
        self.assertFalse(self.backend.key_down(KEY_F9))
        xtest.fake_input(self.observer, X.KeyPress, code)
        self.observer.sync()
        self.addCleanup(xtest.fake_input, self.observer, X.KeyRelease, code)
        self.assertTrue(self.backend.key_down(KEY_F9))
        self.assertFalse(self.backend.key_down(KEY_ESCAPE))

    def test_key_down_follows_the_left_mouse_button(self):
        self.assertFalse(self.backend.key_down(KEY_LEFT_BUTTON))
        xtest.fake_input(self.observer, X.ButtonPress, 1)
        self.observer.sync()
        self.assertTrue(self.backend.key_down(KEY_LEFT_BUTTON))
        xtest.fake_input(self.observer, X.ButtonRelease, 1)
        self.observer.sync()
        self.assertFalse(self.backend.key_down(KEY_LEFT_BUTTON))

    def test_click_delivers_a_button_press_at_the_requested_spot(self):
        self.backend.click(50, 40)
        presses = [ev for ev in self.drain_events() if ev.type == X.ButtonPress]
        self.assertEqual([(ev.detail, ev.event_x, ev.event_y) for ev in presses],
                         [(1, 50, 40)])
        self.assertEqual(self.backend.cursor_pos(), (50, 40))

    def test_foreground_reports_the_focused_window(self):
        self.assertEqual(self.backend.foreground(), self.window.id)

    def test_focus_moves_input_focus_to_the_window(self):
        other = self.make_window(300, 300)
        self.backend.focus(other.id)
        self.assertEqual(self.backend.foreground(), other.id)

    def test_focus_on_a_destroyed_window_does_not_raise(self):
        other = self.make_window(300, 300)
        handle = other.id
        self.destroy(other)
        self.backend.focus(handle)

    def test_root_window_at_finds_the_window_under_the_point(self):
        self.assertEqual(self.backend.root_window_at(50, 40), self.window.id)

    def test_window_title_reads_the_utf8_name(self):
        self.window.change_property(
            self.observer.intern_atom("_NET_WM_NAME"), self.observer.intern_atom("UTF8_STRING"),
            8, "Tëst ✓".encode(),
        )
        self.observer.sync()
        self.assertEqual(self.backend.window_title(self.window.id), "Tëst ✓")

    def test_window_title_reads_the_legacy_name(self):
        self.window.set_wm_name("legacy title")
        self.observer.sync()
        self.assertEqual(self.backend.window_title(self.window.id), "legacy title")

    def test_window_title_is_empty_for_a_destroyed_window(self):
        other = self.make_window(300, 300)
        handle = other.id
        self.destroy(other)
        self.assertEqual(self.backend.window_title(handle), "")


@unittest.skipUnless(HAS_DISPLAY and OPENBOX, "needs an X display and the openbox window manager")
class OpenboxIntegration(unittest.TestCase):
    """The focus guard compares ``foreground()`` with ``root_window_at()`` under a real WM."""

    @classmethod
    def setUpClass(cls):
        # Xvfb resets when its last client leaves; one open connection avoids
        # racing the reset between tests.
        cls.keep_alive = display.Display()

    @classmethod
    def tearDownClass(cls):
        cls.keep_alive.close()

    def setUp(self):
        self.clear_window_manager_properties()
        self.window_manager = subprocess.Popen(
            [OPENBOX], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.addCleanup(self.stop_window_manager)
        self.wait_for(self.window_manager_is_running)
        self.backend = LinuxInput()
        self.addCleanup(self.backend.close)
        self.window = self.open_client_window()
        self.spot = self.point_inside(self.window)

    def point_inside(self, window):
        """Screen coordinates of a point well inside the window, wherever the WM put it."""
        root = self.keep_alive.screen().root
        origin = root.translate_coords(window, INSIDE_OFFSET, INSIDE_OFFSET)
        return origin.x, origin.y

    def clear_window_manager_properties(self):
        """Forget the previous window manager so the readiness check waits for this one."""
        root = self.keep_alive.screen().root
        for name in STALE_ROOT_PROPERTIES:
            root.delete_property(self.keep_alive.intern_atom(name))
        self.keep_alive.sync()

    def stop_window_manager(self):
        self.window_manager.terminate()
        self.window_manager.wait(timeout=WM_START_TIMEOUT)
        self.clear_window_manager_properties()

    def wait_for(self, condition):
        deadline = time.monotonic() + WM_START_TIMEOUT
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(WM_POLL_INTERVAL)
        self.fail(f"timed out waiting for {condition.__name__}")

    def window_manager_is_running(self):
        atom = self.keep_alive.intern_atom("_NET_SUPPORTING_WM_CHECK")
        root = self.keep_alive.screen().root
        return root.get_full_property(atom, X.AnyPropertyType) is not None

    def open_client_window(self):
        screen = self.keep_alive.screen()
        window = screen.root.create_window(
            100, 100, 200, 100, 0, screen.root_depth, X.InputOutput, X.CopyFromParent,
            event_mask=X.KeyPressMask,
        )
        window.set_wm_name("WM client")
        window.map()
        self.keep_alive.sync()
        self.addCleanup(window.destroy)
        self.activate(window)
        return window

    def activate(self, window):
        """Make ``window`` the active one.

        A freshly started window manager can miss the first activation request,
        so keep asking until it reports the client as active.
        """
        deadline = time.monotonic() + WM_START_TIMEOUT
        while time.monotonic() < deadline:
            self.backend.focus(window.id)
            if self.backend.foreground() == window.id:
                return
            time.sleep(WM_POLL_INTERVAL)
        self.fail("the window manager did not activate the client window")

    def test_the_active_window_is_the_client_that_root_window_at_finds(self):
        self.assertEqual(self.backend.root_window_at(*self.spot), self.window.id)
        self.assertEqual(self.backend.foreground(), self.window.id)

    def test_clicking_the_client_keeps_both_ids_equal(self):
        self.backend.click(*self.spot)
        self.assertEqual(self.backend.foreground(), self.backend.root_window_at(*self.spot))

    def test_the_title_comes_from_the_client_not_the_frame(self):
        handle = self.backend.root_window_at(*self.spot)
        self.assertEqual(self.backend.window_title(handle), "WM client")

    def test_focus_returns_to_the_client_after_another_window_takes_it(self):
        other = self.keep_alive.screen().root.create_window(
            400, 400, 100, 100, 0, self.keep_alive.screen().root_depth, X.InputOutput,
            X.CopyFromParent,
        )
        other.set_wm_name("other")
        other.map()
        self.keep_alive.sync()
        self.addCleanup(other.destroy)
        self.activate(other)
        self.backend.focus(self.window.id)
        self.wait_for(lambda: self.backend.foreground() == self.window.id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
