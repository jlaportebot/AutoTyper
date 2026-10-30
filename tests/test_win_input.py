"""Unit tests for the Windows input structure helpers.

These do not call Win32 APIs; they only validate the ctypes layout that the
real SendInput calls depend on.
"""

import ctypes
import unittest

from autotyper.keys import KEY_ESCAPE, KEY_F9, KEY_LEFT_BUTTON
from autotyper.win_input import (
    SYMBOLIC_TO_VK,
    VK_ESCAPE,
    VK_F9,
    VK_LBUTTON,
    WindowsInput,
    build_input_structs,
)

KEY_DOWN_BIT = 0x8000


class RecordingUser32:
    """Answers GetAsyncKeyState for a fixed set of held virtual keys."""

    def __init__(self, held=()):
        self.held = set(held)
        self.queried = []

    def GetAsyncKeyState(self, vk):
        self.queried.append(vk)
        return KEY_DOWN_BIT if vk in self.held else 0


def make_backend(held=()):
    """A WindowsInput without a real user32, for testing key lookups."""
    backend = WindowsInput.__new__(WindowsInput)
    backend.user32 = RecordingUser32(held)
    return backend


class KeyDown(unittest.TestCase):
    def test_symbolic_names_map_to_win32_virtual_keys(self):
        self.assertEqual(
            SYMBOLIC_TO_VK,
            {KEY_ESCAPE: VK_ESCAPE, KEY_F9: VK_F9, KEY_LEFT_BUTTON: VK_LBUTTON},
        )

    def test_symbolic_escape_queries_the_escape_virtual_key(self):
        backend = make_backend(held={VK_ESCAPE})
        self.assertTrue(backend.key_down(KEY_ESCAPE))
        self.assertEqual(backend.user32.queried, [VK_ESCAPE])

    def test_symbolic_left_button_uses_get_async_key_state(self):
        backend = make_backend(held={VK_LBUTTON})
        self.assertTrue(backend.key_down(KEY_LEFT_BUTTON))
        self.assertEqual(backend.user32.queried, [VK_LBUTTON])

    def test_legacy_virtual_key_integers_still_work(self):
        backend = make_backend(held={VK_F9})
        self.assertTrue(backend.key_down(VK_F9))
        self.assertFalse(backend.key_down(VK_ESCAPE))

    def test_released_key_is_reported_up(self):
        self.assertFalse(make_backend().key_down(KEY_F9))

    def test_unknown_symbolic_name_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "enter"):
            make_backend().key_down("enter")

    def test_user32_is_untouched_for_an_unknown_name(self):
        backend = make_backend()
        with self.assertRaises(ValueError):
            backend.key_down("enter")
        self.assertEqual(backend.user32.queried, [])


class InputStructs(unittest.TestCase):
    def test_input_size_matches_platform(self):
        input_struct, _keybd, _mouse = build_input_structs(ctypes)
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(input_struct), expected)

    def test_keyboard_input_fields(self):
        _input, keybd, _mouse = build_input_structs(ctypes)
        fields = [name for name, _type in keybd._fields_]
        self.assertEqual(fields, ["wVk", "wScan", "dwFlags", "time", "dwExtraInfo"])

    def test_mouse_input_fields(self):
        _input, _keybd, mouse = build_input_structs(ctypes)
        fields = [name for name, _type in mouse._fields_]
        self.assertEqual(fields, ["dx", "dy", "mouseData", "dwFlags", "time", "dwExtraInfo"])

    def test_utf16_surrogate_pair_for_emoji(self):
        data = "😀".encode("utf-16-le")
        units = [int.from_bytes(data[i:i + 2], "little") for i in (0, 2)]
        self.assertEqual(units, [0xD83D, 0xDE00])


if __name__ == "__main__":
    unittest.main(verbosity=2)
