"""Smoke tests for the Tkinter UI.

These need a display. On Linux CI they run under ``xvfb-run``; when no
display is available the whole module is skipped.
"""

import gc
import os
import random
import tempfile
import threading
import unittest
from unittest import mock

from autotyper import gui
from autotyper.errors import InputBackendError
from autotyper.gui import AutoTyperApp, font_candidates
from autotyper.keys import FORMAT_BOLD, FORMAT_ITALIC, FORMAT_UNDERLINE, KEY_ESCAPE, KEY_LEFT_BUTTON
from autotyper.richtext import Run, Style
from autotyper.typos import BACKSPACE, final_text

HAS_DISPLAY = bool(os.environ.get("DISPLAY")) or os.name == "nt"

TARGET = 111
WORKER_JOIN_TIMEOUT = 5.0
SESSION_TIMEOUT = 20.0


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

    def toggle_format(self, key):
        self.out.append(key)

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
        with mock.patch.object(gui, "create_backend", side_effect=failure), mock.patch.object(
            gui, "_show_startup_error"
        ) as show:
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
        with mock.patch("sys.platform", "linux"), mock.patch.object(
            gui, "AutoTyperApp", return_value=app
        ):
            self.assertEqual(gui.run(), 0)
        app.run.assert_called_once_with()


@unittest.skipUnless(HAS_DISPLAY, "no display available")
class UserInterface(unittest.TestCase):
    def setUp(self):
        self.config_dir = tempfile.TemporaryDirectory()
        patcher = mock.patch(
            "autotyper.settings.config_base_dir", return_value=self.config_dir.name
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.config_dir.cleanup)
        self.backend = FakeBackend()
        self.app = AutoTyperApp(backend=self.backend, rng=random.Random(11))
        self.app.update()

    def tearDown(self):
        self.app.close()
        for thread in threading.enumerate():
            if thread is not threading.main_thread():
                thread.join(timeout=WORKER_JOIN_TIMEOUT)
        # Finalise this app's Tk objects here, on the main thread. Left to the
        # garbage collector they can be freed on a later test's worker thread,
        # where tkinter blocks for a second per object waiting for a main loop.
        del self.app
        gc.collect()

    def test_run_closes_the_input_backend_when_the_event_loop_ends(self):
        self.backend.close = mock.Mock()
        with mock.patch.object(self.app.root, "mainloop"):
            self.app.run()
        self.backend.close.assert_called_once_with()

    def test_run_closes_the_backend_even_if_the_event_loop_fails(self):
        self.backend.close = mock.Mock()
        with mock.patch.object(
            self.app.root, "mainloop", side_effect=KeyboardInterrupt
        ), self.assertRaises(KeyboardInterrupt):
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

    def set_text(self, text):
        self.app.text_box.delete("1.0", "end")
        self.app.text_box.insert("1.0", text)
        self.app.refresh()

    def run_session(self, text):
        """Start a session, skip the real-time waits and pump the UI until it ends."""
        self.app._finish_pick((120, 240))
        self.set_text(text)
        self.app.slider_delay.set(1)
        self.app.go()
        typist = self.app.state["typist"]
        typist.sleep = lambda _seconds: None
        deadline = gui.time.monotonic() + SESSION_TIMEOUT
        while self.app.message_label.cget("text") == "" and gui.time.monotonic() < deadline:
            self.app.update()
            gui.time.sleep(0.01)
        return typist

    def test_mistakes_section_has_typo_sliders(self):
        self.assertTrue(self.app.slider_typos.winfo_exists())
        self.assertTrue(self.app.slider_catch.winfo_exists())

    def test_typo_sliders_start_from_the_saved_settings(self):
        from autotyper.settings import DEFAULTS

        self.assertEqual(self.app.slider_typos.get(), DEFAULTS["typos"])
        self.assertEqual(self.app.slider_catch.get(), DEFAULTS["catch"])

    def test_session_with_typos_fixes_every_mistake(self):
        text = "The quick brown fox jumps over the lazy dog. " * 8
        self.app.slider_typos.set(10)
        self.app.slider_catch.set(6)
        typist = self.run_session(text)
        self.assertEqual(typist.result, "done")
        self.assertIn(BACKSPACE, self.backend.out)
        self.assertEqual(final_text(self.backend.out), text)
        self.assertEqual(self.app.message_label.cget("text"), "Done.")

    def test_session_without_typos_types_no_backspace(self):
        text = "The quick brown fox jumps over the lazy dog. " * 8
        self.app.slider_typos.set(0)
        typist = self.run_session(text)
        self.assertEqual(typist.result, "done")
        self.assertEqual("".join(self.backend.out), text)

    def test_eta_includes_the_time_spent_fixing_typos(self):
        self.set_text("The quick brown fox jumps over the lazy dog. " * 40)
        self.app.slider_typos.set(0)
        self.app.refresh()
        without = self.app.eta_label.cget("text")
        self.app.slider_typos.set(10)
        self.app.slider_catch.set(15)
        self.app.refresh()
        self.assertNotEqual(self.app.eta_label.cget("text"), without)

    def test_typo_settings_are_persisted(self):
        self.app.slider_typos.set(6)
        self.app.slider_catch.set(4)
        self.app.persist()
        from autotyper.settings import load_settings

        saved = load_settings()
        self.assertEqual((saved["typos"], saved["catch"]), (6, 4))

    def test_stopped_message_counts_characters_left_in_the_field(self):
        self.app._apply_state("stopped", "12/40")
        self.assertIn("12 of 40 characters", self.app.message_label.cget("text"))

    FORMATTED_HTML = (
        '<b style="font-weight:normal"><p><span style="font-weight:400">Plain </span>'
        '<span style="font-weight:700">bold</span><span style="font-style:italic"> slanted</span>'
        '</p><p><u>under</u><span style="white-space:pre-wrap">\tline</span></p></b>'
    )
    FORMATTED_TEXT = "Plain bold slanted\nunder\tline"

    def paste_html(self, html):
        with mock.patch.object(gui, "read_clipboard_html", return_value=html) as read:
            result = self.app._on_paste()
        self.app.update()
        return result, read

    def test_formatting_is_on_by_default(self):
        self.assertTrue(self.app.formatting)
        self.assertIn("on", self.app.format_button.cget("text").lower())

    def test_toggling_formatting_updates_the_button(self):
        self.app.toggle_formatting()
        self.assertFalse(self.app.formatting)
        self.assertIn("off", self.app.format_button.cget("text").lower())

    def test_pasting_formatted_html_keeps_bold_italic_underline_and_spacing(self):
        self.set_text("")
        result, _read = self.paste_html(self.FORMATTED_HTML)
        self.assertEqual(result, "break")
        self.assertEqual(self.app.current_text(), self.FORMATTED_TEXT)
        self.assertEqual(
            self.app.editor_runs(),
            [
                Run("Plain ", Style.PLAIN),
                Run("bold", Style.BOLD),
                Run(" slanted", Style.ITALIC),
                Run("\n", Style.PLAIN),
                Run("under", Style.UNDERLINE),
                Run("\tline", Style.PLAIN),
            ],
        )
        self.assertIn("font", self.app.message_label.cget("text").lower())

    def test_pasting_replaces_the_selection(self):
        self.set_text("keep REPLACE keep")
        self.app.text_box.tag_add("sel", "1.5", "1.12")
        self.paste_html("<b>new</b>")
        self.assertEqual(self.app.current_text(), "keep new keep")

    def test_pasted_bold_and_italic_together_show_in_both(self):
        self.set_text("")
        self.paste_html("<b><i>both</i></b>")
        self.assertIn("font-bold-italic", self.app.text_box.tag_names("1.1"))

    def test_plain_clipboard_falls_back_to_the_normal_paste(self):
        result, _read = self.paste_html(None)
        self.assertIsNone(result)

    def test_html_without_formatting_falls_back_to_the_normal_paste(self):
        result, _read = self.paste_html("<p>just text</p>")
        self.assertIsNone(result)

    def test_paste_with_formatting_off_does_not_read_html(self):
        self.app.toggle_formatting()
        result, read = self.paste_html(self.FORMATTED_HTML)
        self.assertIsNone(result)
        read.assert_not_called()

    def select(self, start, end):
        self.app.text_box.tag_remove("sel", "1.0", "end")
        self.app.text_box.tag_add("sel", start, end)

    def test_shortcut_formats_the_selection_and_toggles_back(self):
        self.set_text("hello world")
        self.select("1.0", "1.5")
        self.assertEqual(self.app.toggle_style(Style.BOLD), "break")
        self.assertEqual(
            self.app.editor_runs(), [Run("hello", Style.BOLD), Run(" world", Style.PLAIN)]
        )
        self.app.toggle_style(Style.BOLD)
        self.assertEqual(self.app.editor_runs(), [Run("hello world", Style.PLAIN)])

    def test_shortcut_on_a_partly_formatted_selection_formats_all_of_it(self):
        self.set_text("hello world")
        self.select("1.0", "1.5")
        self.app.toggle_style(Style.ITALIC)
        self.select("1.0", "1.11")
        self.app.toggle_style(Style.ITALIC)
        self.assertEqual(self.app.editor_runs(), [Run("hello world", Style.ITALIC)])

    def test_shortcut_without_a_selection_changes_nothing(self):
        self.set_text("hello")
        self.app.text_box.tag_remove("sel", "1.0", "end")
        self.app.toggle_style(Style.UNDERLINE)
        self.assertEqual(self.app.editor_runs(), [Run("hello", Style.PLAIN)])

    def test_control_b_is_bound_in_the_editor(self):
        self.assertTrue(self.app.text_box.bind("<Control-b>"))
        self.assertTrue(self.app.text_box.bind("<Control-i>"))
        self.assertTrue(self.app.text_box.bind("<Control-u>"))

    def test_session_types_formatting_shortcuts_around_styled_text(self):
        self.set_text("")
        self.paste_html(self.FORMATTED_HTML)
        self.app.slider_typos.set(0)
        typist = self.run_session_on_current_text()
        self.assertEqual(typist.result, "done")
        self.assertEqual(
            self.backend.out,
            [
                *"Plain ",
                FORMAT_BOLD,
                *"bold",
                FORMAT_BOLD,
                FORMAT_ITALIC,
                *" slanted",
                FORMAT_ITALIC,
                "\n",
                FORMAT_UNDERLINE,
                *"under",
                FORMAT_UNDERLINE,
                *"\tline",
            ],
        )

    def test_session_with_formatting_and_typos_still_types_the_exact_text(self):
        self.set_text("")
        self.paste_html(self.FORMATTED_HTML * 6)
        self.app.slider_typos.set(10)
        self.app.slider_catch.set(6)
        text = self.app.current_text()
        typist = self.run_session_on_current_text()
        self.assertEqual(typist.result, "done")
        self.assertEqual(final_text(self.backend.out), text)
        self.assertIn(FORMAT_BOLD, self.backend.out)

    def test_formatting_off_types_styled_text_as_plain_text(self):
        self.set_text("")
        self.paste_html(self.FORMATTED_HTML)
        self.app.toggle_formatting()
        self.app.slider_typos.set(0)
        typist = self.run_session_on_current_text()
        self.assertEqual(typist.result, "done")
        self.assertEqual("".join(self.backend.out), self.FORMATTED_TEXT)

    def test_formatting_and_styles_are_saved_and_restored(self):
        self.set_text("")
        self.paste_html(self.FORMATTED_HTML)
        runs = self.app.editor_runs()
        self.app.toggle_formatting()
        self.app.persist()
        restored = AutoTyperApp(backend=FakeBackend(), rng=random.Random(1))
        self.addCleanup(restored.close)
        self.assertEqual(restored.editor_runs(), runs)
        self.assertFalse(restored.formatting)

    def test_opening_an_html_file_keeps_its_formatting(self):
        path = os.path.join(self.config_dir.name, "page.html")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("<html><body><p>Hi <b>there</b></p></body></html>")
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=path):
            self.app.open_file()
        self.assertEqual(
            self.app.editor_runs(), [Run("Hi ", Style.PLAIN), Run("there", Style.BOLD)]
        )

    def run_session_on_current_text(self):
        """Like ``run_session`` but keeps the editor's current (formatted) contents."""
        self.app._finish_pick((120, 240))
        self.app.slider_delay.set(1)
        self.app.go()
        typist = self.app.state["typist"]
        typist.sleep = lambda _seconds: None
        deadline = gui.time.monotonic() + SESSION_TIMEOUT
        while self.app.message_label.cget("text") in ("", gui.FORMAT_HINT):
            if gui.time.monotonic() > deadline:
                break
            self.app.update()
            gui.time.sleep(0.01)
        return typist

    def test_breaks_start_off(self):
        self.assertEqual(self.app.slider_rest_every.get(), 0)
        self.assertFalse(self.app.rest_settings().enabled)

    def test_break_settings_are_persisted(self):
        self.app.slider_rest_every.set(15)
        self.app.slider_rest_for.set(3)
        self.app.persist()
        from autotyper.settings import load_settings

        saved = load_settings()
        self.assertEqual((saved["rest_every"], saved["rest_for"]), (15, 3))

    def test_eta_includes_breaks(self):
        self.set_text("The quick brown fox jumps over the lazy dog. " * 40)
        self.app.slider_typos.set(0)
        self.app.slider_rest_every.set(0)
        self.app.refresh()
        without = self.app.eta_label.cget("text")
        self.app.slider_rest_every.set(5)
        self.app.slider_rest_for.set(10)
        self.app.refresh()
        self.assertNotEqual(self.app.eta_label.cget("text"), without)

    def test_session_takes_breaks_and_still_types_the_exact_text(self):
        text = "The quick brown fox jumps over the lazy dog. " * 10
        self.app.slider_typos.set(0)
        self.app.slider_wpm.set(60)
        self.app.slider_rest_every.set(5)
        self.app.slider_rest_for.set(2)
        typist = self.run_session(text)
        self.assertEqual(typist.result, "done")
        self.assertEqual("".join(self.backend.out), text)
        long_waits = [delay for _, delay in typist.plan if delay >= 1.4]
        self.assertGreaterEqual(len(long_waits), 3)

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
