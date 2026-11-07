"""End to end: real keystrokes, with typos and their fixes, land in a real text box.

The real X11 backend sends every key, Backspace included, through the X server
into a Tk text widget, and the test reads back what the widget ends up holding.
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

from autotyper.engine import Typist
from autotyper.gui import AutoTyperApp
from autotyper.pacing import plan_delays
from autotyper.typos import BACKSPACE, typo_settings

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
        self.box = tk.Text(self.target)
        self.box.pack(fill="both", expand=True)
        pump(self.app.root, SETTLE_SECONDS)

    def tearDown(self):
        self.app.close()
        self.app.backend.close()
        for thread in threading.enumerate():
            if thread is not threading.main_thread():
                thread.join(timeout=WORKER_JOIN_TIMEOUT)
        del self.app
        gc.collect()

    def test_go_types_with_typos_and_leaves_the_exact_text(self):
        app = self.app
        app._finish_pick(SPOT)
        app.text_box.insert("1.0", TEXT)
        app.slider_wpm.set(200)
        app.slider_delay.set(1)
        app.slider_typos.set(10)
        app.slider_catch.set(6)
        app.go()
        deadline = time.monotonic() + SESSION_TIMEOUT
        while app.message_label.cget("text") == "" and time.monotonic() < deadline:
            pump(app.root, PUMP_INTERVAL)
        pump(app.root, SETTLE_SECONDS)
        self.assertEqual(app.message_label.cget("text"), "Done.")
        self.assertIn(BACKSPACE, [char for char, _ in app.state["typist"].plan])
        self.assertEqual(self.box.get("1.0", "end-1c"), TEXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
