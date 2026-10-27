"""Self-test for AutoTyper's engine. Run:  python test_autotyper.py"""
import importlib.machinery, importlib.util, os, random, threading, unittest

_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "autotyper.pyw")
spec = importlib.util.spec_from_loader("autotyper", importlib.machinery.SourceFileLoader("autotyper", _path))
at = importlib.util.module_from_spec(spec)
spec.loader.exec_module(at)

TARGET, OTHER = 111, 222


class Fake:
    """Simulated Windows: records keystrokes; script() runs on every sleep tick."""
    def __init__(self):
        self.out, self.keys, self.fg, self.focus_calls, self.ticks = [], set(), TARGET, 0, 0
        self.script = lambda f: None
    def type_char(self, ch):
        assert self.fg == TARGET, "typed into the wrong window!"
        self.out.append(ch)
    def key_down(self, vk): return vk in self.keys
    def foreground(self): return self.fg
    def focus(self, h): self.focus_calls += 1; self.fg = h
    def sleep(self, s): self.ticks += 1; self.script(self)


def make(text, fake=None, **kw):
    fake = fake or Fake()
    plan = at.plan_delays(text, 120, 0.3, random.Random(7))
    t = at.Typist(fake, plan, target=TARGET, sleep=fake.sleep, resume_countdown=1, **kw)
    return t, fake


TEXT = "Hello there.\nThis is a test, with tabs\tand émojis 😀 中文!"


class Engine(unittest.TestCase):
    def test_exact_output_many_seeds(self):
        for seed in range(150):
            for s in [TEXT, "", "a" * 500, "x\n\ny"]:
                f = Fake()
                plan = at.plan_delays(s, 80, 0.5, random.Random(seed))
                t = at.Typist(f, plan, target=TARGET, sleep=f.sleep)
                self.assertEqual(t.run(), "done")
                self.assertEqual("".join(f.out), s)

    def test_pause_button_resumes_at_exact_char(self):
        for pause_at in [0, 1, 5, 13, 30, len(TEXT) - 1]:
            t, f = make(TEXT)
            log = {"paused_at": None, "len_while_paused": set()}
            def prog(i, n, t=t):
                if i == pause_at: t.pause()
            t.on_progress = prog
            if pause_at == 0: t.pause()
            def script(fk, t=t):
                if t.paused and t._resume.is_set() is False:
                    log["len_while_paused"].add(len(fk.out))
                    if fk.ticks % 40 == 0:
                        fk.fg = OTHER        # user clicked Resume in our window
                        t.resume()
            f.script = script
            self.assertEqual(t.run(), "done")
            self.assertEqual("".join(f.out), TEXT, f"pause_at={pause_at}")
            self.assertEqual(log["len_while_paused"], {pause_at}, "typed while paused")
            self.assertGreaterEqual(f.focus_calls, 1, "should refocus target on resume")

    def test_many_pauses(self):
        t, f = make(TEXT * 3)
        def script(fk):
            if fk.ticks % 97 == 0: t.toggle()
        f.script = script
        self.assertEqual(t.run(), "done")
        self.assertEqual("".join(f.out), TEXT * 3)

    def test_f9_toggles(self):
        t, f = make(TEXT)
        seq = {"phase": 0}
        def script(fk):
            # press F9 at tick 50 (pause), release, press again at 150 (resume)
            fk.keys = {at.VK_F9} if fk.ticks in (50, 51, 150, 151) else set()
            if fk.ticks == 100: seq["mid"] = len(fk.out); seq["paused"] = t.paused
        f.script = script
        self.assertEqual(t.run(), "done")
        self.assertTrue(seq["paused"])
        self.assertEqual("".join(f.out), TEXT)

    def test_focus_loss_auto_pauses(self):
        t, f = make(TEXT)
        states = []
        t.on_state = lambda s, i="": states.append((s, i))
        def script(fk):
            if len(fk.out) == 10 and fk.ticks < 2000 and not t.paused and not states[-1][0] == "resuming":
                fk.fg = OTHER  # user clicked another window
            if t.paused and fk.ticks % 60 == 0:
                t.resume()
        f.script = script
        self.assertEqual(t.run(), "done")
        self.assertEqual("".join(f.out), TEXT)
        self.assertTrue(any(s == "paused" and "switched" in i for s, i in states))

    def test_stop_while_paused(self):
        t, f = make(TEXT)
        t.on_progress = lambda i, n: i == 7 and t.pause()
        f.script = lambda fk: t.paused and fk.ticks % 30 == 0 and t.stop()
        self.assertEqual(t.run(), "stopped")
        self.assertEqual("".join(f.out), TEXT[:7])

    def test_escape_stops(self):
        t, f = make(TEXT)
        f.script = lambda fk: len(fk.out) >= 4 and fk.keys.add(at.VK_ESCAPE)
        self.assertEqual(t.run(), "stopped")
        self.assertEqual("".join(f.out), TEXT[:4])

    def test_escape_while_paused(self):
        t, f = make(TEXT)
        t.pause()
        f.script = lambda fk: fk.ticks == 20 and fk.keys.add(at.VK_ESCAPE)
        self.assertEqual(t.run(), "stopped")
        self.assertEqual(f.out, [])

    def test_pause_during_resume_countdown(self):
        t, f = make(TEXT)
        states = []
        t.on_state = lambda s, i="": states.append(s)
        t.on_progress = lambda i, n: i == 3 and t.pause()
        def script(fk):
            if t.paused and not t._resume.is_set() and states.count("resuming") < 2 and fk.ticks % 25 == 0:
                t.resume()
            elif states and states[-1] == "resuming" and states.count("resuming") == 1 and not t.paused:
                t.pause()                    # pause again mid-countdown
        f.script = script
        self.assertEqual(t.run(), "done")
        self.assertEqual("".join(f.out), TEXT)

    def test_speed_matches_wpm(self):
        text = "the quick brown fox jumps over the lazy dog " * 50
        for wpm in (30, 60, 120):
            actual = (len(text) / 5) / (at.estimate_seconds(text, wpm, 0.25) / 60)
            self.assertTrue(0.6 * wpm < actual < 1.05 * wpm, (wpm, actual))

    def test_fmt_time(self):
        self.assertEqual(at.fmt_time(65), "1:05")
        self.assertEqual(at.fmt_time(3725), "1:02:05")

    def test_struct_layout(self):
        import ctypes
        INPUT, KI, MI = at.build_input_structs(ctypes)
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_utf16_surrogates(self):
        data = "😀".encode("utf-16-le")
        self.assertEqual([int.from_bytes(data[i:i+2], "little") for i in (0, 2)], [0xD83D, 0xDE00])

    def test_settings_roundtrip(self):
        import tempfile
        d = tempfile.mkdtemp(); old = os.environ.get("APPDATA"); os.environ["APPDATA"] = d
        try:
            at.save_settings({"wpm": 90, "variation": 10, "delay": 5, "text": "hi"})
            self.assertEqual(at.load_settings()["wpm"], 90)
        finally:
            if old is None: os.environ.pop("APPDATA")
            else: os.environ["APPDATA"] = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
