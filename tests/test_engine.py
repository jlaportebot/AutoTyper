"""Unit tests for the typing engine.

The engine is exercised against a fake input backend so the whole suite
runs on any platform.
"""

import random
import unittest
from typing import Callable

from autotyper.engine import Typist
from autotyper.keys import FORMAT_BOLD, FORMAT_UNDERLINE, KEY_ESCAPE, KEY_F9
from autotyper.pacing import plan_delays
from autotyper.typos import BACKSPACE, final_text, typo_settings

TARGET = 111
OTHER = 222
SIBLING = 112
MAX_TICKS = 5000
TEXT = "Hello there.\nThis is a test, with tabs\tand émojis 😀 中文!"


class FakeBackend:
    """Records keystrokes; ``script`` runs on every sleep tick."""

    def __init__(self):
        self.out = []
        self.keys = set()
        self.fg = TARGET
        self.focus_calls = 0
        self.ticks = 0
        self.script: Callable[FakeBackend, None] = lambda backend: None

    def type_char(self, char):
        assert self.fg == TARGET, "typed into the wrong window!"
        self.out.append(char)

    def key_down(self, key):
        return key in self.keys

    def foreground(self):
        return self.fg

    def toggle_format(self, key):
        assert self.fg == TARGET, "toggled formatting in the wrong window!"
        self.out.append(key)

    def focus(self, handle):
        self.focus_calls += 1
        self.fg = handle

    def sleep(self, _seconds):
        self.ticks += 1
        self.script(self)


class ApplicationFocusBackend(FakeBackend):
    """Like macOS: focusing activates the application, whose front window may differ."""

    def __init__(self, front_after_focus):
        super().__init__()
        self.front_after_focus = front_after_focus

    def type_char(self, char):
        assert self.fg in (TARGET, SIBLING), "typed into another application!"
        self.out.append(char)

    def focus(self, handle):
        self.focus_calls += 1
        self.fg = self.front_after_focus

    def same_application(self, first, second):
        return {first, second} <= {TARGET, SIBLING}


def make_typist(text=TEXT, backend=None, wpm=120, variation=0.3, **kwargs):
    """Build a Typist wired to a fake backend."""
    backend = backend or FakeBackend()
    plan = plan_delays(text, wpm, variation, random.Random(7))
    kwargs.setdefault("resume_countdown", 1)
    return Typist(backend, plan, target=TARGET, sleep=backend.sleep, **kwargs), backend


class EngineOutput(unittest.TestCase):
    def test_exact_output_across_many_seeds(self):
        for seed in range(150):
            for text in (TEXT, "", "a" * 500, "x\n\ny"):
                backend = FakeBackend()
                plan = plan_delays(text, 80, 0.5, random.Random(seed))
                typist = Typist(backend, plan, target=TARGET, sleep=backend.sleep)
                self.assertEqual(typist.run(), "done")
                self.assertEqual("".join(backend.out), text)

    def test_unicode_and_emoji_survive(self):
        typist, backend = make_typist("émoji 😀 中文")
        typist.run()
        self.assertEqual("".join(backend.out), "émoji 😀 中文")


class EngineWithTypos(unittest.TestCase):
    def make(self, text=TEXT * 4, seed=3):
        backend = FakeBackend()
        plan = plan_delays(text, 120, 0.3, random.Random(seed), typo_settings(10, 6))
        typist = Typist(backend, plan, target=TARGET, sleep=backend.sleep, resume_countdown=1)
        return typist, backend

    def test_backspaces_are_sent_and_the_field_ends_up_correct(self):
        for seed in range(20):
            typist, backend = self.make(seed=seed)
            self.assertEqual(typist.run(), "done")
            self.assertIn(BACKSPACE, backend.out)
            self.assertEqual(final_text(backend.out), TEXT * 4)

    def test_finished_session_reports_text_characters_not_keystrokes(self):
        typist, _backend = self.make()
        infos = []
        typist.on_state = lambda state, info="": infos.append((state, info))
        typist.run()
        total = len(TEXT * 4)
        self.assertEqual(infos[-1], ("done", f"{total}/{total}"))

    def test_stopped_session_reports_what_is_left_in_the_field(self):
        typist, backend = self.make()
        infos = []
        typist.on_state = lambda state, info="": infos.append((state, info))
        typist.on_progress = lambda index, _total: index == 150 and typist.stop()
        self.assertEqual(typist.run(), "stopped")
        visible = len(final_text(backend.out))
        self.assertEqual(infos[-1], ("stopped", f"{visible}/{len(TEXT * 4)}"))

    def test_abort_reports_zero_of_the_text_length(self):
        typist, _backend = self.make()
        infos = []
        typist.on_state = lambda state, info="": infos.append((state, info))
        typist.abort()
        self.assertEqual(infos, [("stopped", f"0/{len(TEXT * 4)}")])

    def test_pause_and_resume_in_the_middle_of_a_fix(self):
        typist, backend = self.make()
        first_backspace = [char for char, _ in typist.plan].index(BACKSPACE)
        typist.on_progress = lambda index, _total: index == first_backspace and typist.pause()
        backend.script = lambda fake: typist.paused and fake.ticks % 50 == 0 and typist.resume()
        self.assertEqual(typist.run(), "done")
        self.assertEqual(final_text(backend.out), TEXT * 4)


class EngineWithFormatting(unittest.TestCase):
    def test_shortcuts_go_to_toggle_format_and_text_to_type_char(self):
        keys = ["a", FORMAT_BOLD, "b", FORMAT_BOLD, FORMAT_UNDERLINE, "c", FORMAT_UNDERLINE]
        backend = FakeBackend()
        typed = []
        backend.type_char = lambda char: typed.append(char)
        plan = [(key, 0.01) for key in keys]
        typist = Typist(backend, plan, target=TARGET, sleep=backend.sleep)
        self.assertEqual(typist.run(), "done")
        shortcuts = [FORMAT_BOLD, FORMAT_BOLD, FORMAT_UNDERLINE, FORMAT_UNDERLINE]
        self.assertEqual(backend.out, shortcuts)
        self.assertEqual(typed, ["a", "b", "c"])

    def test_shortcuts_do_not_count_as_typed_characters(self):
        plan = [(key, 0.01) for key in ["a", FORMAT_BOLD, "b", FORMAT_BOLD]]
        backend = FakeBackend()
        infos = []
        typist = Typist(backend, plan, target=TARGET, sleep=backend.sleep)
        typist.on_state = lambda state, info="": infos.append((state, info))
        typist.run()
        self.assertEqual(infos[-1], ("done", "2/2"))


class EngineControl(unittest.TestCase):
    def test_pause_button_resumes_at_exact_character(self):
        for pause_at in (0, 1, 5, 13, 30, len(TEXT) - 1):
            typist, backend = make_typist()
            seen = {"paused_at": None, "lengths": set()}

            def progress(index, _total, typist=typist, seen=seen):
                if index == pause_at:
                    typist.pause()

            typist.on_progress = progress
            if pause_at == 0:
                typist.pause()

            def script(fake, typist=typist, seen=seen):
                if typist.paused and not typist._resume.is_set():
                    seen["lengths"].add(len(fake.out))
                    if fake.ticks % 40 == 0:
                        fake.fg = OTHER
                        typist.resume()

            backend.script = script
            self.assertEqual(typist.run(), "done")
            self.assertEqual("".join(backend.out), TEXT, f"pause_at={pause_at}")
            self.assertEqual(seen["lengths"], {pause_at}, "typed while paused")
            self.assertGreaterEqual(backend.focus_calls, 1, "should refocus target on resume")

    def test_many_pauses(self):
        typist, backend = make_typist(TEXT * 3)
        backend.script = lambda fake: typist.toggle() if fake.ticks % 97 == 0 else None
        self.assertEqual(typist.run(), "done")
        self.assertEqual("".join(backend.out), TEXT * 3)

    def test_f9_toggles_pause_and_resume(self):
        typist, backend = make_typist()
        observed = {}

        def script(fake):
            fake.keys = {KEY_F9} if fake.ticks in (50, 51, 150, 151) else set()
            if fake.ticks == 100:
                observed["mid"] = len(fake.out)
                observed["paused"] = typist.paused

        backend.script = script
        self.assertEqual(typist.run(), "done")
        self.assertTrue(observed["paused"])
        self.assertEqual("".join(backend.out), TEXT)

    def test_focus_loss_auto_pauses(self):
        typist, backend = make_typist()
        states = []
        typist.on_state = lambda state, info="": states.append((state, info))

        def script(fake):
            switched = not states or states[-1][0] != "resuming"
            if len(fake.out) == 10 and fake.ticks < 2000 and not typist.paused and switched:
                fake.fg = OTHER
            if typist.paused and fake.ticks % 60 == 0:
                typist.resume()

        backend.script = script
        self.assertEqual(typist.run(), "done")
        self.assertEqual("".join(backend.out), TEXT)
        self.assertTrue(any(s == "paused" and "switched" in i for s, i in states))

    def run_with_a_manual_pause(self, backend):
        """Pause once after 10 characters and resume whenever paused; capped in ticks."""
        typist, backend = make_typist(backend=backend)
        states = []
        typist.on_state = lambda state, info="": states.append((state, info))
        paused_once = []

        def script(fake):
            if len(fake.out) == 10 and not paused_once:
                paused_once.append(True)
                typist.pause()
            if typist.paused and fake.ticks % 60 == 0:
                typist.resume()
            if fake.ticks > MAX_TICKS:
                typist.stop()

        backend.script = script
        return backend, states, typist.run()

    def test_resume_accepts_another_window_of_the_same_application(self):
        backend = ApplicationFocusBackend(front_after_focus=SIBLING)
        backend, states, result = self.run_with_a_manual_pause(backend)
        self.assertEqual(result, "done")
        self.assertEqual("".join(backend.out), TEXT)
        self.assertEqual(backend.focus_calls, 1)
        self.assertFalse(any("switched" in info for _state, info in states))

    def test_resume_still_pauses_when_another_application_comes_forward(self):
        backend = ApplicationFocusBackend(front_after_focus=OTHER)
        backend, states, result = self.run_with_a_manual_pause(backend)
        self.assertEqual(result, "stopped")
        self.assertEqual(len(backend.out), 10)
        self.assertTrue(any("switched" in info for _state, info in states))

    def test_resume_without_same_application_support_keeps_the_strict_check(self):
        backend = FakeBackend()
        backend, states, result = self.run_with_a_manual_pause(backend)
        self.assertEqual(result, "done")
        self.assertFalse(any("switched" in info for _state, info in states))

    def test_stop_while_paused(self):
        typist, backend = make_typist()
        typist.on_progress = lambda index, _total: index == 7 and typist.pause()

        def script(fake):
            if typist.paused and fake.ticks % 30 == 0:
                typist.stop()

        backend.script = script
        self.assertEqual(typist.run(), "stopped")
        self.assertEqual("".join(backend.out), TEXT[:7])

    def test_escape_stops(self):
        typist, backend = make_typist()

        def script(fake):
            if len(fake.out) >= 4:
                fake.keys.add(KEY_ESCAPE)

        backend.script = script
        self.assertEqual(typist.run(), "stopped")
        self.assertEqual("".join(backend.out), TEXT[:4])

    def test_escape_while_paused(self):
        typist, backend = make_typist()
        typist.pause()

        def script(fake):
            if fake.ticks == 20:
                fake.keys.add(KEY_ESCAPE)

        backend.script = script
        self.assertEqual(typist.run(), "stopped")
        self.assertEqual(backend.out, [])

    def test_pause_during_resume_countdown(self):
        typist, backend = make_typist()
        states = []
        typist.on_state = lambda state, info="": states.append(state)
        typist.on_progress = lambda index, _total: index == 3 and typist.pause()

        def script(fake):
            resuming_once = states and states[-1] == "resuming" and states.count("resuming") == 1
            if typist.paused and not typist._resume.is_set() and states.count("resuming") < 2:
                if fake.ticks % 25 == 0:
                    typist.resume()
            elif resuming_once and not typist.paused:
                typist.pause()

        backend.script = script
        self.assertEqual(typist.run(), "done")
        self.assertEqual("".join(backend.out), TEXT)

    def test_stopped_property_reflects_stop(self):
        typist, _backend = make_typist()
        self.assertFalse(typist.stopped)
        typist.stop()
        self.assertTrue(typist.stopped)

    def test_toggle_requests_resume_when_paused(self):
        typist, _backend = make_typist()
        typist.pause()
        self.assertTrue(typist.paused)
        typist.toggle()
        self.assertTrue(typist._resume.is_set())

    def test_engine_clears_paused_flag_after_resume(self):
        typist, backend = make_typist()
        backend.script = lambda fake: typist.toggle() if fake.ticks % 97 == 0 else None
        self.assertEqual(typist.run(), "done")
        self.assertFalse(typist.paused)
        self.assertEqual("".join(backend.out), TEXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
