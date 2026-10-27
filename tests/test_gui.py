"""Smoke tests for the Tkinter UI.

These need a display. On Linux CI they run under ``xvfb-run``; when no
display is available the whole module is skipped.
"""

import os
import unittest

from autotyper.gui import AutoTyperApp

HAS_DISPLAY = bool(os.environ.get("DISPLAY")) or os.name == "nt"

TARGET = 111


class FakeBackend:
    """Stands in for the Windows input layer."""

    def __init__(self):
        self.out = []
        self.keys = set()
        self.fg = TARGET
        self.clicks = []
        self.focus_calls = 0
        self.title = "Notepad"

    def type_char(self, char):
        self.out.append(char)

    def key_down(self, vk):
        return vk in self.keys

    def foreground(self):
        return self.fg

    def focus(self, hwnd):
        self.focus_calls += 1
        self.fg = hwnd

    def cursor_pos(self):
        return (120, 240)

    def root_window_at(self, x, y):
        return TARGET

    def window_title(self, hwnd):
        return self.title

    def click(self, x, y):
        self.clicks.append((x, y))


@unittest.skipUnless(HAS_DISPLAY, "no display available")
class UserInterface(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.app = AutoTyperApp(backend=self.backend)
        self.app.update()

    def tearDown(self):
        self.app.close()

    def test_window_builds_with_all_sections(self):
        self.assertTrue(self.app.go_button.winfo_exists())
        self.assertTrue(self.app.text_box.winfo_exists())
        self.assertTrue(self.app.pick_button.winfo_exists())
        self.assertTrue(self.app.slider_wpm.winfo_exists())
        self.assertTrue(self.app.slider_delay.winfo_exists())

    def test_counters_update_with_the_text(self):
        self.app.text_box.delete("1.0", "end")
        self.app.text_box.insert("1.0", "hello world")
        self.app.refresh()
        self.assertIn("11", self.app.count_label.cget("text"))
        self.assertIn("2", self.app.count_label.cget("text"))
        self.assertTrue(self.app.eta_label.cget("text"))

    def test_pick_records_the_target_window(self):
        self.app._finish_pick((120, 240))
        self.assertEqual(self.app.state["spot"], (120, 240))
        self.assertEqual(self.app.state["hwnd"], TARGET)
        self.assertIn("Notepad", self.app.spot_label.cget("text"))

    def test_cancelled_pick_leaves_no_target(self):
        self.app._finish_pick(None)
        self.assertIsNone(self.app.state["spot"])
        self.assertIn("cancelled", self.app.message_label.cget("text"))

    def test_go_without_text_is_rejected(self):
        self.app.text_box.delete("1.0", "end")
        self.app.go()
        self.assertIn("text", self.app.message_label.cget("text"))

    def test_go_without_target_is_rejected(self):
        self.app.text_box.delete("1.0", "end")
        self.app.text_box.insert("1.0", "hello")
        self.app.go()
        self.assertIn("spot", self.app.message_label.cget("text"))

    def test_go_clicks_the_spot_and_types_the_text(self):
        self.app._finish_pick((120, 240))
        self.app.text_box.delete("1.0", "end")
        self.app.text_box.insert("1.0", "hi")
        self.app.slider_delay.set(1)
        self.app.slider_wpm.set(200)
        self.app.go()
        typist = self.app.state["typist"]
        for _ in range(200):
            self.app.update()
            if typist.result is not None:
                break
            typist.sleep(0.05)
        self.assertEqual(typist.result, "done")
        self.assertEqual("".join(self.backend.out), "hi")
        self.assertEqual(self.backend.clicks, [(120, 240)])

    def test_stop_button_stops_the_session(self):
        self.app._finish_pick((120, 240))
        self.app.text_box.delete("1.0", "end")
        self.app.text_box.insert("1.0", "a much longer piece of text to type out")
        self.app.slider_delay.set(1)
        self.app.slider_wpm.set(20)
        self.app.go()
        typist = self.app.state["typist"]
        self.app.stop_typing()
        for _ in range(200):
            self.app.update()
            if typist.result is not None:
                break
            typist.sleep(0.05)
        self.assertEqual(typist.result, "stopped")

    def test_settings_roundtrip_through_the_ui(self):
        self.app.text_box.delete("1.0", "end")
        self.app.text_box.insert("1.0", "remember me")
        self.app.slider_wpm.set(123)
        self.app.persist()
        from autotyper.settings import load_settings

        self.assertEqual(load_settings()["wpm"], 123)
        self.assertEqual(load_settings()["text"], "remember me")


if __name__ == "__main__":
    unittest.main(verbosity=2)
