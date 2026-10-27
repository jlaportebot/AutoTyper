"""
AutoTyper - types text into any field on Windows, one key at a time.

  Pick spot -> enter text -> Go.
  F9  = pause / resume (continues from the exact character)
  Esc = stop

Requires Windows + Python 3.8+ (tkinter ships with the python.org installer).
No other packages.
"""

import json
import os
import random
import sys
import threading
import time

APP = "AutoTyper"
VK_RETURN, VK_TAB, VK_ESCAPE, VK_LBUTTON, VK_F9, VK_MENU = 0x0D, 0x09, 0x1B, 0x01, 0x78, 0x12


# ===========================================================================
# Pacing (pure logic)
# ===========================================================================

def plan_delays(text, wpm=60, variation=0.25, rng=None):
    """List of (char, delay_before_char_seconds). 1 word = 5 chars."""
    rng = rng or random.Random()
    wpm = max(5, min(400, float(wpm)))
    variation = max(0.0, min(0.9, float(variation)))
    base = 60.0 / (wpm * 5)
    out, prev = [], ""
    for ch in text:
        d = base * rng.uniform(1 - variation, 1 + variation)
        if prev == " ":
            d *= 1.3
        elif prev in ",;:":
            d += base * rng.uniform(2, 4)
        elif prev in ".!?":
            d += base * rng.uniform(4, 8)
        elif prev == "\n":
            d += base * rng.uniform(6, 12)
        out.append((ch, max(0.005, d)))
        prev = ch
    return out


def estimate_seconds(text, wpm=60, variation=0.25):
    return sum(d for _, d in plan_delays(text, wpm, variation, random.Random(0)))


def fmt_time(secs):
    secs = int(round(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ===========================================================================
# Typing engine - works with any backend that has:
#   type_char(ch), key_down(vk) -> bool, foreground() -> id, focus(id)
# ===========================================================================

class Typist:
    def __init__(self, backend, plan, target=None, on_progress=None, on_state=None,
                 resume_countdown=2, sleep=time.sleep):
        self.b, self.plan, self.target = backend, plan, target
        self.on_progress = on_progress or (lambda i, n: None)
        self.on_state = on_state or (lambda state, info="": None)
        self.resume_countdown = resume_countdown
        self.sleep = sleep
        self.pos = 0                       # next character to type
        self._remaining = None             # delay left before plan[pos]
        self._pause = threading.Event()
        self._resume = threading.Event()
        self._stop = threading.Event()
        self._f9_prev = False
        self.pause_reason = ""
        self.result = None

    # --- control (thread-safe, callable from GUI) ---------------------------
    def pause(self, reason="Paused"):
        if not self._stop.is_set() and not self._pause.is_set():
            self.pause_reason = reason
            self._resume.clear()
            self._pause.set()

    def resume(self):
        if self._pause.is_set():
            self._resume.set()

    def toggle(self):
        self.resume() if self._pause.is_set() else self.pause()

    def stop(self):
        self._stop.set()
        self._resume.set()

    @property
    def paused(self):
        return self._pause.is_set()

    # --- helpers ------------------------------------------------------------
    def _f9_pressed(self):
        down = self.b.key_down(VK_F9)
        edge = down and not self._f9_prev
        self._f9_prev = down
        return edge

    def _esc(self):
        return self.b.key_down(VK_ESCAPE)

    def _wait(self):
        """Sleep off the current char's remaining delay in slices.
        Returns False if interrupted (pause/stop); remaining time is kept for later."""
        while self._remaining > 0:
            if self._stop.is_set() or self._esc():
                self._stop.set()
                return False
            if self._f9_pressed():
                self.pause("Paused (F9)")
            if self._pause.is_set():
                return False
            step = min(0.02, self._remaining)
            self.sleep(step)
            self._remaining -= step
        return True

    def _wait_for_resume(self):
        self.on_state("paused", self.pause_reason)
        while not self._resume.is_set():
            if self._stop.is_set() or self._esc():
                self._stop.set()
                return False
            if self._f9_pressed():
                self._resume.set()
                break
            self.sleep(0.02)
        if self._stop.is_set():
            return False
        self._pause.clear()
        self._resume.clear()
        for n in range(self.resume_countdown, 0, -1):
            self.on_state("resuming", str(n))
            for _ in range(50):
                if self._stop.is_set() or self._esc():
                    self._stop.set()
                    return False
                if self._pause.is_set():          # paused again during countdown
                    return True
                self.sleep(0.02)
        if self.target is not None:
            self.b.focus(self.target)
            self.sleep(0.25)
        self.on_state("typing", "")
        return True

    # --- main loop ----------------------------------------------------------
    def run(self):
        self.on_state("typing", "")
        n = len(self.plan)
        while self.pos < n:
            if self._stop.is_set():
                break
            if self._pause.is_set():
                if not self._wait_for_resume():
                    break
                continue
            ch, delay = self.plan[self.pos]
            if self._remaining is None:
                self._remaining = delay
            if not self._wait():
                continue
            if self.target is not None and self.b.foreground() != self.target:
                self.pause("Paused - you switched windows")
                continue
            self.b.type_char(ch)
            self.pos += 1
            self._remaining = None
            self.on_progress(self.pos, n)
        self.result = "done" if self.pos >= n else "stopped"
        self.on_state(self.result, f"{self.pos}/{n}")
        return self.result


# ===========================================================================
# Windows input layer (SendInput via ctypes)
# ===========================================================================

def build_input_structs(ctypes):
    """SendInput structures with fixed-size fields (INPUT = 40 bytes on 64-bit)."""
    LONG, DWORD, WORD = ctypes.c_int32, ctypes.c_uint32, ctypes.c_uint16
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD), ("dwFlags", DWORD),
                    ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD), ("time", DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", DWORD), ("u", _U)]

    return INPUT, KEYBDINPUT, MOUSEINPUT


class WindowsInput:
    INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
    KEYUP, UNICODE = 0x0002, 0x0004
    LEFTDOWN, LEFTUP = 0x0002, 0x0004

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wt = ctypes, wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                self.user32.SetProcessDPIAware()
            except Exception:
                pass
        self.INPUT, self.KEYBDINPUT, self.MOUSEINPUT = build_input_structs(ctypes)
        u = self.user32
        u.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(self.INPUT), ctypes.c_int)
        u.SendInput.restype = wintypes.UINT
        u.WindowFromPoint.argtypes = (wintypes.POINT,)
        u.WindowFromPoint.restype = wintypes.HWND
        u.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        u.GetAncestor.restype = wintypes.HWND
        u.GetForegroundWindow.restype = wintypes.HWND
        u.SetForegroundWindow.argtypes = (wintypes.HWND,)
        u.IsIconic.argtypes = (wintypes.HWND,)
        u.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        u.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)

    def _send(self, *inputs):
        arr = (self.INPUT * len(inputs))(*inputs)
        n = self.user32.SendInput(len(inputs), arr, self.ctypes.sizeof(self.INPUT))
        if n != len(inputs):
            raise OSError("Windows blocked the keystroke (target app may be running as administrator)")

    def _key(self, vk=0, scan=0, flags=0):
        i = self.INPUT(type=self.INPUT_KEYBOARD)
        i.ki = self.KEYBDINPUT(vk, scan, flags, 0, 0)
        return i

    def press_vk(self, vk):
        self._send(self._key(vk=vk), self._key(vk=vk, flags=self.KEYUP))

    def type_char(self, ch):
        if ch == "\n":
            return self.press_vk(VK_RETURN)
        if ch == "\t":
            return self.press_vk(VK_TAB)
        if ch == "\r":
            return
        data = ch.encode("utf-16-le")
        units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
        self._send(*[self._key(scan=x, flags=self.UNICODE) for x in units],
                   *[self._key(scan=x, flags=self.UNICODE | self.KEYUP) for x in units])

    def key_down(self, vk):
        return bool(self.user32.GetAsyncKeyState(vk) & 0x8000)

    def cursor_pos(self):
        p = self.wt.POINT()
        self.user32.GetCursorPos(self.ctypes.byref(p))
        return p.x, p.y

    def root_window_at(self, x, y):
        h = self.user32.WindowFromPoint(self.wt.POINT(int(x), int(y)))
        return self.user32.GetAncestor(h, 2) if h else None  # GA_ROOT

    def window_title(self, hwnd):
        buf = self.ctypes.create_unicode_buffer(256)
        self.user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value

    def foreground(self):
        return self.user32.GetForegroundWindow()

    def focus(self, hwnd):
        if not hwnd:
            return
        if self.user32.IsIconic(hwnd):
            self.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        # tapping Alt lets Windows hand focus to another window
        self.press_vk(VK_MENU)
        self.user32.SetForegroundWindow(hwnd)

    def click(self, x, y):
        self.user32.SetCursorPos(int(x), int(y))
        time.sleep(0.05)
        a = self.INPUT(type=self.INPUT_MOUSE); a.mi = self.MOUSEINPUT(0, 0, 0, self.LEFTDOWN, 0, 0)
        b = self.INPUT(type=self.INPUT_MOUSE); b.mi = self.MOUSEINPUT(0, 0, 0, self.LEFTUP, 0, 0)
        self._send(a, b)


# ===========================================================================
# Settings
# ===========================================================================

DEFAULTS = {"wpm": 65, "variation": 25, "delay": 3, "text": ""}


def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP, "settings.json")


def load_settings():
    try:
        with open(settings_path(), encoding="utf-8") as f:
            return {**DEFAULTS, **json.load(f)}
    except Exception:
        return dict(DEFAULTS)


def save_settings(s):
    try:
        os.makedirs(os.path.dirname(settings_path()), exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(s, f)
    except Exception:
        pass


# ===========================================================================
# GUI
# ===========================================================================

C = {
    "bg": "#0e0f12", "panel": "#15171c", "line": "#24272f", "field": "#101216",
    "text": "#e8e6e3", "dim": "#6f7480", "accent": "#c8f560", "accent_dk": "#9cc43f",
    "warn": "#ffb547", "bad": "#ff6b5e",
}


def main():
    import tkinter as tk
    from tkinter import filedialog, font as tkfont

    if sys.platform != "win32":
        print("AutoTyper only runs on Windows.")
        return

    win = WindowsInput()
    cfg = load_settings()
    st = {"spot": None, "hwnd": None, "typist": None}

    root = tk.Tk()
    root.title(APP)
    root.configure(bg=C["bg"])
    root.geometry("600x640")
    root.minsize(500, 560)
    root.attributes("-topmost", True)

    fams = set(tkfont.families())
    UI = next((f for f in ("Segoe UI Variable Text", "Segoe UI") if f in fams), "TkDefaultFont")
    MONO = next((f for f in ("Cascadia Mono", "Consolas") if f in fams), "TkFixedFont")
    f_ui, f_ui_b = (UI, 10), (UI, 10, "bold")
    f_label, f_mono = (MONO, 8), (MONO, 10)
    f_title = (UI, 18, "bold")

    # ---------- tiny widget kit ----------
    class Btn(tk.Label):
        def __init__(self, master, text, cmd, kind="ghost", **kw):
            self.kind, self.cmd, self.enabled = kind, cmd, True
            super().__init__(master, text=text, font=f_ui_b, padx=16, pady=7, cursor="hand2", **kw)
            self._paint(False)
            self.bind("<Enter>", lambda e: self._paint(True))
            self.bind("<Leave>", lambda e: self._paint(False))
            self.bind("<Button-1>", lambda e: self.enabled and self.cmd())

        def _paint(self, hover):
            if not self.enabled:
                self.config(bg=C["panel"], fg=C["line"]); return
            if self.kind == "primary":
                self.config(bg=C["accent"] if not hover else C["accent_dk"], fg="#0b0c0e")
            else:
                self.config(bg=C["line"] if hover else C["panel"], fg=C["text"])

        def set(self, text=None, enabled=None, kind=None):
            if text is not None: self.config(text=text)
            if enabled is not None:
                self.enabled = enabled
                self.config(cursor="hand2" if enabled else "arrow")
            if kind is not None: self.kind = kind
            self._paint(False)

    def section(parent, num, title):
        wrap = tk.Frame(parent, bg=C["bg"])
        wrap.pack(fill="x", padx=22, pady=(14, 0))
        head = tk.Frame(wrap, bg=C["bg"]); head.pack(fill="x")
        tk.Label(head, text=num, font=f_label, fg=C["accent"], bg=C["bg"]).pack(side="left")
        tk.Label(head, text="  " + title.upper(), font=f_label, fg=C["dim"], bg=C["bg"]).pack(side="left")
        tk.Frame(head, bg=C["line"], height=1).pack(side="left", fill="x", expand=True, padx=(10, 0), pady=(2, 0))
        body = tk.Frame(wrap, bg=C["bg"]); body.pack(fill="x", pady=(8, 0))
        return wrap, body

    class Slider(tk.Frame):
        def __init__(self, master, label, lo, hi, value, unit="", on_change=None):
            super().__init__(master, bg=C["bg"])
            self.var = tk.IntVar(value=value)
            self.unit, self.on_change = unit, on_change
            tk.Label(self, text=label, font=f_ui, fg=C["text"], bg=C["bg"], width=14, anchor="w").pack(side="left")
            tk.Scale(self, from_=lo, to=hi, orient="horizontal", variable=self.var, showvalue=0,
                     bg=C["bg"], troughcolor=C["line"], activebackground=C["accent"],
                     highlightthickness=0, bd=0, sliderrelief="flat", sliderlength=14, width=6,
                     command=self._changed).pack(side="left", fill="x", expand=True, padx=8)
            self.val = tk.Label(self, font=f_mono, fg=C["accent"], bg=C["bg"], width=7, anchor="e")
            self.val.pack(side="left")
            self.val.config(text=f"{value}{unit}")   # no callback during construction

        def _changed(self, *_):
            self.val.config(text=f"{self.var.get()}{self.unit}")
            if self.on_change: self.on_change()

        def get(self):
            return self.var.get()

    # ---------- MAIN VIEW ----------
    main_view = tk.Frame(root, bg=C["bg"])
    main_view.pack(fill="both", expand=True)

    hdr = tk.Frame(main_view, bg=C["bg"]); hdr.pack(fill="x", padx=22, pady=(20, 0))
    tk.Label(hdr, text="autotyper", font=f_title, fg=C["text"], bg=C["bg"]).pack(side="left")
    tk.Label(hdr, text="_", font=f_title, fg=C["accent"], bg=C["bg"]).pack(side="left")
    tk.Label(hdr, text="F9 pause · ESC stop", font=f_label, fg=C["dim"], bg=C["bg"]).pack(side="right", pady=(8, 0))

    # 01 target
    _, b1 = section(main_view, "01", "Target")
    spot_dot = tk.Label(b1, text="●", font=f_ui, fg=C["line"], bg=C["bg"]); spot_dot.pack(side="left")
    spot_lbl = tk.Label(b1, text="No spot picked", font=f_ui, fg=C["dim"], bg=C["bg"], anchor="w")
    spot_lbl.pack(side="left", padx=(6, 0), fill="x", expand=True)
    pick_btn = Btn(b1, "Pick spot", lambda: pick()); pick_btn.pack(side="right")

    # 02 text
    w2, b2 = section(main_view, "02", "Text")
    w2.pack_configure(fill="both", expand=True)
    b2.pack_configure(fill="both", expand=True)
    box = tk.Frame(b2, bg=C["line"], padx=1, pady=1); box.pack(fill="both", expand=True)
    txt = tk.Text(box, wrap="word", undo=True, font=(UI, 11), bg=C["field"], fg=C["text"],
                  insertbackground=C["accent"], selectbackground="#2f3a1a", relief="flat",
                  padx=12, pady=10, height=8, highlightthickness=0)
    txt.pack(fill="both", expand=True)
    txt.insert("1.0", cfg["text"])
    tools = tk.Frame(b2, bg=C["bg"]); tools.pack(fill="x", pady=(6, 0))
    count_lbl = tk.Label(tools, font=f_label, fg=C["dim"], bg=C["bg"]); count_lbl.pack(side="left")
    Btn(tools, "Clear", lambda: (txt.delete("1.0", "end"), refresh())).pack(side="right")
    Btn(tools, "Open .txt", lambda: open_file()).pack(side="right", padx=(0, 6))

    # 03 speed
    _, b3 = section(main_view, "03", "Speed & timing")
    s_wpm = Slider(b3, "Words / minute", 10, 200, cfg["wpm"], "", lambda: refresh())
    s_var = Slider(b3, "Rhythm", 0, 60, cfg["variation"], "%", lambda: refresh())
    s_delay = Slider(b3, "Start delay", 1, 10, cfg["delay"], "s", lambda: refresh())
    for s in (s_wpm, s_var, s_delay): s.pack(fill="x", pady=1)

    # footer
    foot = tk.Frame(main_view, bg=C["bg"]); foot.pack(fill="x", padx=22, pady=(16, 20))
    eta_lbl = tk.Label(foot, font=f_mono, fg=C["dim"], bg=C["bg"]); eta_lbl.pack(side="left")
    go_btn = Btn(foot, "Go  →", lambda: go(), kind="primary"); go_btn.pack(side="right")
    msg_lbl = tk.Label(main_view, text="", font=f_ui, fg=C["warn"], bg=C["bg"])
    msg_lbl.pack(fill="x", padx=22, pady=(0, 10))

    # ---------- MINI BAR (shown while typing) ----------
    mini = tk.Frame(root, bg=C["panel"], highlightthickness=1, highlightbackground=C["line"])
    mrow = tk.Frame(mini, bg=C["panel"]); mrow.pack(fill="x", padx=12, pady=(10, 6))
    m_state = tk.Label(mrow, text="TYPING", font=f_label, fg=C["accent"], bg=C["panel"]); m_state.pack(side="left")
    m_pct = tk.Label(mrow, font=f_mono, fg=C["text"], bg=C["panel"]); m_pct.pack(side="right")
    bar = tk.Canvas(mini, height=4, bg=C["line"], highlightthickness=0); bar.pack(fill="x", padx=12)
    bar_fill = bar.create_rectangle(0, 0, 0, 4, fill=C["accent"], width=0)
    m_info = tk.Label(mini, text="", font=f_ui, fg=C["dim"], bg=C["panel"], anchor="w")
    m_info.pack(fill="x", padx=12, pady=(6, 0))
    mbtns = tk.Frame(mini, bg=C["panel"]); mbtns.pack(fill="x", padx=12, pady=(6, 12))
    m_pause = Btn(mbtns, "Pause", lambda: st["typist"] and st["typist"].toggle(), bg=C["panel"])
    m_pause.pack(side="left")
    Btn(mbtns, "Stop", lambda: st["typist"] and st["typist"].stop()).pack(side="right")

    # ---------- logic ----------
    def refresh():
        t = txt.get("1.0", "end-1c")
        words = len(t.split())
        count_lbl.config(text=f"{len(t):,} CHARS · {words:,} WORDS")
        eta_lbl.config(text=f"≈ {fmt_time(estimate_seconds(t, s_wpm.get(), s_var.get()/100))}" if t else "")

    def persist():
        save_settings({"wpm": s_wpm.get(), "variation": s_var.get(), "delay": s_delay.get(),
                       "text": txt.get("1.0", "end-1c")})

    def say(m, color=C["warn"]):
        msg_lbl.config(text=m, fg=color)

    def open_file():
        p = filedialog.askopenfilename(filetypes=[("Text", "*.txt *.md"), ("All files", "*.*")])
        if p:
            with open(p, encoding="utf-8", errors="replace") as f:
                txt.delete("1.0", "end"); txt.insert("1.0", f.read().replace("\r\n", "\n"))
            refresh()

    def pick():
        pick_btn.set(enabled=False)
        root.iconify()

        def wait_click():
            time.sleep(0.4)
            while win.key_down(VK_LBUTTON): time.sleep(0.01)
            got, t0 = None, time.time()
            while time.time() - t0 < 30:
                if win.key_down(VK_ESCAPE): break
                if win.key_down(VK_LBUTTON):
                    got = win.cursor_pos(); break
                time.sleep(0.01)

            def done():
                root.deiconify(); pick_btn.set(enabled=True)
                if got:
                    st["spot"] = got
                    st["hwnd"] = win.root_window_at(*got)
                    title = win.window_title(st["hwnd"]) or "window"
                    title = title if len(title) < 42 else title[:40] + "…"
                    spot_lbl.config(text=f"{title}   ({got[0]}, {got[1]})", fg=C["text"])
                    spot_dot.config(fg=C["accent"]); say("")
                else:
                    say("Pick cancelled.")
            root.after(0, done)
        threading.Thread(target=wait_click, daemon=True).start()

    def show_mini():
        main_view.pack_forget()
        mini.pack(fill="both", expand=True)
        root.minsize(1, 1)
        w, h = 300, 128
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x, y = sw - w - 24, sh - h - 70
        sx, sy = st["spot"]
        if x - 10 <= sx <= x + w + 10 and y - 40 <= sy <= y + h + 10:
            y = 24  # don't cover the target
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.overrideredirect(True)

    def show_main():
        root.overrideredirect(False)
        mini.pack_forget()
        main_view.pack(fill="both", expand=True)
        root.minsize(500, 560)
        root.geometry("600x640")
        go_btn.set(enabled=True)

    def ui_state(state, info=""):
        def apply():
            if state == "typing":
                m_state.config(text="TYPING", fg=C["accent"]); m_pause.set("Pause"); m_info.config(text="F9 pause · Esc stop")
            elif state == "paused":
                m_state.config(text="PAUSED", fg=C["warn"]); m_pause.set("Resume")
                m_info.config(text=info + " · F9 resume")
            elif state == "resuming":
                m_state.config(text=f"RESUMING IN {info}", fg=C["warn"]); m_info.config(text="Returning to your window…")
            elif state == "countdown":
                m_state.config(text=f"STARTING IN {info}", fg=C["dim"]); m_info.config(text="Esc to cancel")
            elif state in ("done", "stopped"):
                show_main()
                say("Done." if state == "done" else f"Stopped · {info.replace('/', ' of ')} characters typed.",
                    C["accent"] if state == "done" else C["warn"])
        root.after(0, apply)

    def ui_progress(i, n):
        def apply():
            w = bar.winfo_width()
            bar.coords(bar_fill, 0, 0, w * i / max(1, n), 4)
            m_pct.config(text=f"{i * 100 // max(1, n)}%")
        root.after(0, apply)

    def go():
        text = txt.get("1.0", "end-1c")
        if not text: return say("Enter some text first.")
        if not st["spot"]: return say("Pick a spot first.")
        persist()
        plan = plan_delays(text, s_wpm.get(), s_var.get() / 100)
        typist = Typist(win, plan, target=st["hwnd"], on_progress=ui_progress, on_state=ui_state)
        st["typist"] = typist
        go_btn.set(enabled=False)
        show_mini(); ui_progress(0, len(plan))

        def worker():
            try:
                for n in range(s_delay.get(), 0, -1):
                    ui_state("countdown", str(n))
                    for _ in range(10):
                        if win.key_down(VK_ESCAPE) or typist._stop.is_set():
                            return ui_state("stopped", f"0/{len(plan)}")
                        time.sleep(0.1)
                win.click(*st["spot"])
                time.sleep(0.3)
                st["hwnd"] = typist.target = win.foreground()  # window that actually got focus
                typist.run()
            except Exception as e:
                ui_state("stopped", "0")
                root.after(0, lambda: say(f"Error: {e}", C["bad"]))
        threading.Thread(target=worker, daemon=True).start()

    txt.bind("<<Modified>>", lambda e: (refresh(), txt.edit_modified(False)))
    root.protocol("WM_DELETE_WINDOW", lambda: (persist(), st["typist"] and st["typist"].stop(), root.destroy()))
    refresh()
    root.mainloop()


if __name__ == "__main__":
    main()
