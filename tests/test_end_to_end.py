"""End to end: real keystrokes, typos, fixes and formatting land in a real text box.

The real X11 backend sends every key (Backspace and Ctrl+B/I/U included)
through the X server into a Tk text widget, and the test reads back what the
widget ends up holding. Formatted text even arrives through the real clipboard.
It needs an X display and python-xlib, so it runs on Linux (CI uses xvfb-run)
and is skipped elsewhere.
"""

import gc
import os
import random
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

try:
    from autotyper.linux_input import LinuxInput
except ImportError as exc:
    raise unittest.SkipTest(f"python-xlib is not installed: {exc}") from exc

from autotyper.editor import TAG_FOR_STYLE, StyledText
from autotyper.engine import Typist
from autotyper.gui import AutoTyperApp
from autotyper.keys import FORMAT_BOLD, FORMAT_ITALIC, FORMAT_UNDERLINE
from autotyper.pacing import plan_delays, plan_keys
from autotyper.richtext import Style, format_keys, plain_text, runs_from_html
from autotyper.typos import BACKSPACE, typo_settings
from tests.x11_helpers import HtmlClipboardOwner

CAN_TYPE = sys.platform.startswith("linux") and bool(os.environ.get("DISPLAY"))
# ASCII only: characters outside the keymap are typed through a temporary keymap
# entry, which a Tk text box in this same process cannot read in time, and which
# Tk decodes as Latin-1. Separate-process GTK, Qt and browser windows are fine.
TEXT = (
    "The quick brown fox jumps over the lazy dog.\n"
    "Typing like a person means hitting the wrong key now and then,\tnoticing it, "
    "and fixing it before anyone sees. Numbers 1234 and symbols (a+b) = 7!"
)
FAST_WPM = 400
TARGET_GEOMETRY = "420x220+0+0"
SPOT = (120, 60)
SETTLE_SECONDS = 0.4
SESSION_TIMEOUT = 60.0
PUMP_INTERVAL = 0.01
WORKER_JOIN_TIMEOUT = 5.0
RICH_HTML = (
    '<b style="font-weight:normal" id="docs-internal-guid-1"><p>'
    '<span style="font-weight:400">Plain words then </span>'
    '<span style="font-weight:700">bold words</span><span> and </span>'
    '<span style="font-style:italic">italic words</span><span> and </span>'
    '<span style="text-decoration:underline">underlined words</span><span> and </span>'
    '<span style="font-weight:700;font-style:italic">bold italic</span><span> end.</span></p>'
    '<p><span style="white-space:pre-wrap">Second paragraph\twith a tab.</span></p></b>'
)
TARGET_SHORTCUTS = (("b", Style.BOLD), ("i", Style.ITALIC), ("u", Style.UNDERLINE))
STYLE_AFTER_TYPING = "styled-after-typing"


def pump(root, seconds):
    """Let Tk process X events for a while."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.update()
        time.sleep(PUMP_INTERVAL)


@unittest.skipUnless(CAN_TYPE, "needs Linux with an X display")
class EngineIntoARealTextBox(unittest.TestCase):
    def setUp(self):
        import tkinter as tk

        self.root = tk.Tk()
        self.root.geometry(TARGET_GEOMETRY)
        self.box = tk.Text(self.root)
        self.box.pack(fill="both", expand=True)
        pump(self.root, SETTLE_SECONDS)
        self.root.focus_force()
        self.box.focus_set()
        pump(self.root, SETTLE_SECONDS)
        self.backend = LinuxInput()
        self.addCleanup(self.backend.close)

    def tearDown(self):
        self.root.destroy()

    def contents(self):
        return self.box.get("1.0", "end-1c")

    def type_plan(self, plan):
        """Type ``plan`` for real; returns every state the text box went through."""
        seen = []

        def sleep(seconds):
            self.root.update()
            time.sleep(seconds)

        typist = Typist(self.backend, plan, sleep=sleep)
        typist.on_progress = lambda _index, _total: seen.append(self.contents())
        self.assertEqual(typist.run(), "done")
        pump(self.root, SETTLE_SECONDS)
        return seen

    def test_mistakes_appear_on_screen_and_are_fixed(self):
        plan = plan_delays(TEXT, FAST_WPM, 0.2, random.Random(5), typo_settings(10, 6))
        self.assertIn(BACKSPACE, [char for char, _ in plan])
        seen = self.type_plan(plan)
        self.assertEqual(self.contents(), TEXT)
        wrong = [state for state in seen if not TEXT.startswith(state)]
        self.assertTrue(wrong, "no mistake was ever visible in the text box")

    def test_text_without_typos_is_typed_exactly(self):
        plan = plan_delays(TEXT, FAST_WPM, 0.2, random.Random(5))
        seen = self.type_plan(plan)
        self.assertEqual(self.contents(), TEXT)
        self.assertTrue(all(TEXT.startswith(state) for state in seen))


class RichTarget:
    """A text box that styles what is typed after Ctrl+B/I/U, like a word processor."""

    def __init__(self, parent):
        import tkinter as tk

        self.box = tk.Text(parent)
        self.box.pack(fill="both", expand=True)
        self.reader = StyledText(self.box, "TkDefaultFont", 10)
        self.pending = Style.PLAIN
        for letter, style in TARGET_SHORTCUTS:
            self.box.bind(f"<Control-{letter}>", lambda _event, style=style: self._switch(style))
        toplevel = str(self.box.winfo_toplevel())
        self.box.bindtags((str(self.box), "Text", STYLE_AFTER_TYPING, toplevel, "all"))
        self.box.bind_class(STYLE_AFTER_TYPING, "<KeyPress>", self._style_typed)

    def _switch(self, style):
        self.pending ^= style
        return "break"

    def _style_typed(self, event):
        """Give the character Tk has just inserted the styles that are switched on."""
        if not (event.char.isprintable() or event.char in ("\r", "\t")) or not event.char:
            return
        for style, tag in TAG_FOR_STYLE.items():
            if self.pending & style:
                self.box.tag_add(tag, "insert-1c")

    def runs(self):
        return self.reader.runs()


@unittest.skipUnless(CAN_TYPE, "needs Linux with an X display")
class FormattingIntoARealRichTextBox(unittest.TestCase):
    def setUp(self):
        import tkinter as tk

        self.root = tk.Tk()
        self.root.geometry(TARGET_GEOMETRY)
        self.target = RichTarget(self.root)
        pump(self.root, SETTLE_SECONDS)
        self.root.focus_force()
        self.target.box.focus_set()
        pump(self.root, SETTLE_SECONDS)
        self.backend = LinuxInput()
        self.addCleanup(self.backend.close)

    def tearDown(self):
        self.root.destroy()

    def type_keys(self, keys):
        def sleep(seconds):
            self.root.update()
            time.sleep(seconds)

        plan = plan_keys(keys, FAST_WPM, 0.2, random.Random(3))
        self.assertEqual(Typist(self.backend, plan, sleep=sleep).run(), "done")
        pump(self.root, SETTLE_SECONDS)

    def test_bold_italic_underline_and_spacing_arrive_exactly(self):
        runs = runs_from_html(RICH_HTML)
        keys = format_keys(runs)
        self.assertTrue({FORMAT_BOLD, FORMAT_ITALIC, FORMAT_UNDERLINE} <= set(keys))
        self.type_keys(keys)
        self.assertEqual(self.target.runs(), runs)

    def test_formatting_survives_typos_and_their_fixes(self):
        runs = runs_from_html(RICH_HTML)
        keys = format_keys(runs, typo_settings(10, 6), random.Random(4))
        self.assertIn(BACKSPACE, keys)
        self.type_keys(keys)
        self.assertEqual(self.target.runs(), runs)


@unittest.skipUnless(CAN_TYPE, "needs Linux with an X display")
class WholeAppIntoARealTextBox(unittest.TestCase):
    """Pick a spot, press Go and let the app type into another window, for real."""

    def setUp(self):
        import tkinter as tk

        config_dir = tempfile.TemporaryDirectory()
        self.addCleanup(config_dir.cleanup)
        patcher = mock.patch("autotyper.settings.config_base_dir", return_value=config_dir.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = AutoTyperApp(backend=LinuxInput(), rng=random.Random(8))
        self.target = tk.Toplevel(self.app.root)
        self.target.geometry(TARGET_GEOMETRY)
        self.rich = RichTarget(self.target)
        self.box = self.rich.box
        pump(self.app.root, SETTLE_SECONDS)

    def tearDown(self):
        self.app.close()
        self.app.backend.close()
        for thread in threading.enumerate():
            if thread is not threading.main_thread():
                thread.join(timeout=WORKER_JOIN_TIMEOUT)
        del self.app
        gc.collect()

    def run_session(self):
        """Press Go and wait until the app reports the session finished."""
        app = self.app
        app._finish_pick(SPOT)
        app.slider_wpm.set(200)
        app.slider_delay.set(1)
        app.slider_typos.set(10)
        app.slider_catch.set(6)
        app.say("")
        app.go()
        deadline = time.monotonic() + SESSION_TIMEOUT
        while app.message_label.cget("text") == "" and time.monotonic() < deadline:
            pump(app.root, PUMP_INTERVAL)
        pump(app.root, SETTLE_SECONDS)
        self.assertEqual(app.message_label.cget("text"), "Done.")

    def test_paste_formatted_text_from_the_clipboard_and_type_it_with_styles(self):
        expected = runs_from_html(RICH_HTML)
        with HtmlClipboardOwner(RICH_HTML):
            self.assertEqual(self.app._on_paste(), "break")
        self.assertEqual(self.app.editor_runs(), expected)
        self.run_session()
        self.assertEqual(self.box.get("1.0", "end-1c"), plain_text(expected))
        self.assertEqual(self.rich.runs(), expected)

    def test_go_types_with_typos_and_leaves_the_exact_text(self):
        app = self.app
        app.text_box.insert("1.0", TEXT)
        self.run_session()
        self.assertIn(BACKSPACE, [char for char, _ in app.state["typist"].plan])
        self.assertEqual(self.box.get("1.0", "end-1c"), TEXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
