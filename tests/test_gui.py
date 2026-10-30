"""Smoke tests for the Tkinter UI.

These need a display. On Linux CI they run under ``xvfb-run``; when no
display is available the whole module is skipped.
"""

import os
import tempfile
import unittest
from unittest import mock

from autotyper import gui
from autotyper.errors import InputBackendError
from autotyper.gui import AutoTyperApp, font_candidates
from autotyper.keys import KEY_ESCAPE, KEY_LEFT_BUTTON

HAS_DISPLAY = bool(os.environ.get("DISPLAY")) or os.name == "nt"

TARGET = 111


class FakeBackend:
    """Stands in for the platform input layer."""

    def __init__(self):
        self.out = []
        self.keys = set()
        self.fg = TARGET
        self.clicks = []
        self.focus_calls = 0
        self.title = "Notepad"

    def type_char(self, char):
        self.out.append(char)

    def key_down(self, key):
        return key in self.keys

    def foreground(self):
        return self.fg

    def focus(self, handle):
        self.focus_calls += 1
        self.fg = handle

    def cursor_pos(self):
        return (120, 240)

    def root_window_at(self, x, y):
        return TARGET

    def window_title(self, handle):
        return self.title

    def click(self, x, y):
        self.clicks.append((x, y))


class ScriptedClickBackend(FakeBackend):
    """Reports the left button as released once, then pressed."""

    def __init__(self):
        super().__init__()
        self.left_states = iter([False, True])

    def key_down(self, key):
        if key == KEY_LEFT_BUTTON:
            return next(self.left_states, True)
        return super().key_down(key)


class FontCandidates(unittest.TestCase):
    def test_windows_prefers_segoe_and_cascadia(self):
        ui, mono = font_candidates("win32")
        self.assertEqual(ui, ("Segoe UI Variable Text", "Segoe UI"))
        self.assertEqual(mono, ("Cascadia Mono", "Consolas"))

    def test_macos_prefers_sf_and_menlo(self):
        ui, mono = font_candidates("darwin")
        self.assertEqual(ui, ("SF Pro Text", "Helvetica Neue", "Arial"))
        self.assertEqual(mono, ("SF Mono", "Menlo", "Monaco"))

    def test_linux_prefers_ubuntu_and_dejavu(self):
        ui, mono = font_candidates("linux")
        self.assertEqual(ui, ("Ubuntu", "Cantarell", "DejaVu Sans", "Noto Sans"))
        self.assertEqual(mono, ("DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono"))

    def test_unknown_platform_uses_the_linux_list(self):
        self.assertEqual(font_candidates("freebsd14"), font_candidates("linux"))

    def test_defaults_to_the_running_platform(self):
        with mock.patch("sys.platform", "darwin"):
            self.assertEqual(font_candidates(), font_candidates("darwin"))


class StartupErrors(unittest.TestCase):
    def test_run_reports_an_unavailable_backend_and_returns_failure(self):
        failure = InputBackendError("no input backend")
        with mock.patch.object(gui, "create_backend", side_effect=failure), \
                mock.patch.object(gui, "_show_startup_error") as show:
            self.assertEqual(gui.run(), 1)
        show.assert_called_once_with(failure)

    def test_startup_dialog_survives_a_display_that_raises_an_os_error(self):
        with mock.patch("tkinter.Tk", side_effect=OSError("display went away")):
            gui._show_startup_error(InputBackendError("no input backend"))

    def test_startup_dialog_survives_a_missing_display(self):
        import tkinter

        with mock.patch("tkinter.Tk", side_effect=tkinter.TclError("no display")):
            gui._show_startup_error(InputBackendError("no input backend"))

    def test_run_does_not_hard_fail_on_non_windows_platforms(self):
        app = mock.Mock()
        with mock.patch("sys.platform", "linux"), \
                mock.patch.object(gui, "AutoTyperApp", return_value=app):
            self.assertEqual(gui.run(), 0)
        app.run.assert_called_once_with()


@unittest.skipUnless(HAS_DISPLAY, "no display available")
class UserInterface(unittest.TestCase):
    def setUp(self):
        self.config_dir = tempfile.TemporaryDirectory()
        patcher = mock.patch("autotyper.settings.config_base_dir",
                             return_value=self.config_dir.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.config_dir.cleanup)
        self.backend = FakeBackend()
        self.app = AutoTyperApp(backend=self.backend)
        self.app.update()

    def tearDown(self):
        self.app.close()

    def test_run_closes_the_input_backend_when_the_event_loop_ends(self):
        self.backend.close = mock.Mock()
        with mock.patch.object(self.app.root, "mainloop"):
            self.app.run()
        self.backend.close.assert_called_once_with()

    def test_run_closes_the_backend_even_if_the_event_loop_fails(self):
        self.backend.close = mock.Mock()
        with mock.patch.object(self.app.root, "mainloop", side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            self.app.run()
        self.backend.close.assert_called_once_with()

    def test_run_survives_a_backend_that_cannot_disconnect(self):
        self.backend.close = mock.Mock(side_effect=OSError("broken pipe"))
        with mock.patch.object(self.app.root, "mainloop"):
            self.app.run()

    def test_run_works_with_a_backend_that_has_no_close(self):
        with mock.patch.object(self.app.root, "mainloop"):
            self.app.run()

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
        self.assertEqual(self.app.state["handle"], TARGET)
        self.assertIn("Notepad", self.app.spot_label.cget("text"))

    def test_wait_for_click_records_the_cursor_when_left_button_is_pressed(self):
        self.app.backend = ScriptedClickBackend()
        with mock.patch.object(gui.time, "sleep"):
            self.app._wait_for_click()
        self.assertEqual(self.app.events.get_nowait(), ("pick", (120, 240)))

    def test_wait_for_click_cancels_when_escape_is_held(self):
        self.backend.keys.add(KEY_ESCAPE)
        with mock.patch.object(gui.time, "sleep"):
            self.app._wait_for_click()
        self.assertEqual(self.app.events.get_nowait(), ("pick", None))

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
