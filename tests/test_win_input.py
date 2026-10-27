"""Unit tests for the Windows input structure helpers.

These do not call Win32 APIs; they only validate the ctypes layout that the
real SendInput calls depend on.
"""

import ctypes
import unittest

from autotyper.win_input import build_input_structs


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
