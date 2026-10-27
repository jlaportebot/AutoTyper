"""The AutoTyper desktop UI (Tkinter).

The window mirrors a three-step workflow: pick a target spot, enter the text,
tune the speed, then press Go. While typing, the main window collapses into a
small floating control bar.
"""

import queue
import sys
import threading
import time

from .engine import Typist
from .gui_colors import COLORS
from .pacing import estimate_seconds, fmt_time, plan_delays
from .settings import load_settings, save_settings
from .widgets import Button, Slider
from .win_input import VK_ESCAPE, VK_LBUTTON, WindowsInput

APP_NAME = "AutoTyper"
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 640
MIN_WIDTH = 500
MIN_HEIGHT = 560
MINI_WIDTH = 300
MINI_HEIGHT = 128
MINI_MARGIN = 24
MINI_BOTTOM_GAP = 70
TITLE_MAX_CHARS = 42
PICK_TIMEOUT_SECONDS = 30
PICK_ARM_DELAY = 0.4
CLICK_SETTLE_DELAY = 0.3
COUNTDOWN_TICKS = 10
TEXT_FILE_TYPES = [("Text", "*.txt *.md"), ("All files", "*.*")]
DECODE_ERRORS = "replace"
UI_FONTS = ("Segoe UI Variable Text", "Segoe UI")
MONO_FONTS = ("Cascadia Mono", "Consolas")

STATE_TYPING = "typing"
STATE_PAUSED = "paused"
STATE_RESUMING = "resuming"
STATE_COUNTDOWN = "countdown"
STATE_DONE = "done"
STATE_STOPPED = "stopped"
EVENT_POLL_MS = 40


def _pick_font(available, candidates, fallback):
    """Return the first installed font family from a preference list."""
    for name in candidates:
        if name in available:
            return name
    return fallback


def _shorten_title(title):
    """Trim a window title so it fits the target label."""
    title = title or "window"
    if len(title) < TITLE_MAX_CHARS:
        return title
    return title[: TITLE_MAX_CHARS - 2] + "…"


class AutoTyperApp:
    """Owns the Tk widgets and wires them to the typing engine."""

    def __init__(self, backend=None):
        import tkinter as tk

        self.tk = tk
        self.backend = backend or WindowsInput()
        self.config = load_settings()
        self.state = {"spot": None, "hwnd": None, "typist": None}
        self.events = queue.Queue()
        self.poll_job = None
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=COLORS["bg"])
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.root.attributes("-topmost", True)
        self._build_fonts()
        self._build_ui()
        self._wire_events()
        self.refresh()

    def _build_fonts(self):
        """Resolve the UI font families available on this machine."""
        from tkinter import font as tkfont

        families = set(tkfont.families())
        self.ui = _pick_font(families, UI_FONTS, "TkDefaultFont")
        self.mono = _pick_font(families, MONO_FONTS, "TkFixedFont")
        self.font_ui = (self.ui, 10)
        self.font_ui_bold = (self.ui, 10, "bold")
        self.font_label = (self.mono, 8)
        self.font_mono = (self.mono, 10)
        self.font_title = (self.ui, 18, "bold")

    def _button(self, parent, text, command, kind="ghost", **kwargs):
        """Create a flat button in the current visual style."""
        return Button(parent, text, command, kind, self.font_ui_bold, **kwargs)

    def _slider(self, parent, label, low, high, value, unit="", on_change=None):
        """Create a horizontal slider in the current visual style."""
        return Slider(parent, label, low, high, value, unit, on_change,
                      self.font_ui, self.font_label, self.font_mono)

    def _section(self, parent, number, title):
        """Create a numbered section header and return its body frame."""
        tk = self.tk
        wrap = tk.Frame(parent, bg=COLORS["bg"])
        wrap.pack(fill="x", padx=22, pady=(14, 0))
        head = tk.Frame(wrap, bg=COLORS["bg"])
        head.pack(fill="x")
        tk.Label(head, text=number, font=self.font_label, fg=COLORS["accent"],
                 bg=COLORS["bg"]).pack(side="left")
        tk.Label(head, text="  " + title.upper(), font=self.font_label,
                 fg=COLORS["dim"], bg=COLORS["bg"]).pack(side="left")
        tk.Frame(head, bg=COLORS["line"], height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0), pady=(2, 0)
        )
        body = tk.Frame(wrap, bg=COLORS["bg"])
        body.pack(fill="x", pady=(8, 0))
        return wrap, body

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        """Assemble the whole window."""
        tk = self.tk
        self.main_view = tk.Frame(self.root, bg=COLORS["bg"])
        self.main_view.pack(fill="both", expand=True)

        header = tk.Frame(self.main_view, bg=COLORS["bg"])
        header.pack(fill="x", padx=22, pady=(20, 0))
        tk.Label(header, text="autotyper", font=self.font_title, fg=COLORS["text"],
                 bg=COLORS["bg"]).pack(side="left")
        tk.Label(header, text="_", font=self.font_title, fg=COLORS["accent"],
                 bg=COLORS["bg"]).pack(side="left")
        tk.Label(header, text="F9 pause · ESC stop", font=self.font_label,
                 fg=COLORS["dim"], bg=COLORS["bg"]).pack(side="right", pady=(8, 0))

        self._build_target_section()
        self._build_text_section()
        self._build_speed_section()
        self._build_footer()
        self._build_mini_bar()

    def _build_target_section(self):
        """Section 01: pick the window and spot to type into."""
        tk = self.tk
        _, body = self._section(self.main_view, "01", "Target")
        self.spot_dot = tk.Label(body, text="●", font=self.font_ui, fg=COLORS["line"],
                                 bg=COLORS["bg"])
        self.spot_dot.pack(side="left")
        self.spot_label = tk.Label(body, text="No spot picked", font=self.font_ui,
                                   fg=COLORS["dim"], bg=COLORS["bg"], anchor="w")
        self.spot_label.pack(side="left", padx=(6, 0), fill="x", expand=True)
        self.pick_button = self._button(body, "Pick spot", self.pick)
        self.pick_button.pack(side="right")

    def _build_text_section(self):
        """Section 02: the text editor."""
        tk = self.tk
        wrap, body = self._section(self.main_view, "02", "Text")
        wrap.pack_configure(fill="both", expand=True)
        body.pack_configure(fill="both", expand=True)
        frame = tk.Frame(body, bg=COLORS["line"], padx=1, pady=1)
        frame.pack(fill="both", expand=True)
        self.text_box = tk.Text(
            frame, wrap="word", undo=True, font=(self.ui, 11), bg=COLORS["field"],
            fg=COLORS["text"], insertbackground=COLORS["accent"],
            selectbackground="#2f3a1a", relief="flat", padx=12, pady=10, height=8,
            highlightthickness=0,
        )
        self.text_box.pack(fill="both", expand=True)
        self.text_box.insert("1.0", self.config["text"])

        tools = tk.Frame(body, bg=COLORS["bg"])
        tools.pack(fill="x", pady=(6, 0))
        self.count_label = tk.Label(tools, font=self.font_label, fg=COLORS["dim"],
                                    bg=COLORS["bg"])
        self.count_label.pack(side="left")
        self._button(tools, "Clear", self.clear_text).pack(side="right")
        self._button(tools, "Open .txt", self.open_file).pack(side="right", padx=(0, 6))

    def _build_speed_section(self):
        """Section 03: speed, rhythm and start delay."""
        _, body = self._section(self.main_view, "03", "Speed & timing")
        self.slider_wpm = self._slider(
            body, "Words / minute", 10, 200, self.config["wpm"], "", self.refresh
        )
        self.slider_variation = self._slider(
            body, "Rhythm", 0, 60, self.config["variation"], "%", self.refresh
        )
        self.slider_delay = self._slider(
            body, "Start delay", 1, 10, self.config["delay"], "s", self.refresh
        )
        for slider in (self.slider_wpm, self.slider_variation, self.slider_delay):
            slider.pack(fill="x", pady=1)

    def _build_footer(self):
        """Footer: ETA readout plus the Go button and status line."""
        tk = self.tk
        footer = tk.Frame(self.main_view, bg=COLORS["bg"])
        footer.pack(fill="x", padx=22, pady=(16, 20))
        self.eta_label = tk.Label(footer, font=self.font_mono, fg=COLORS["dim"],
                                  bg=COLORS["bg"])
        self.eta_label.pack(side="left")
        self.go_button = self._button(footer, "Go  →", self.go, kind="primary")
        self.go_button.pack(side="right")
        self.message_label = tk.Label(self.main_view, text="", font=self.font_ui,
                                      fg=COLORS["warn"], bg=COLORS["bg"])
        self.message_label.pack(fill="x", padx=22, pady=(0, 10))

    def _build_mini_bar(self):
        """The floating control bar shown while typing."""
        tk = self.tk
        self.mini = tk.Frame(self.root, bg=COLORS["panel"], highlightthickness=1,
                             highlightbackground=COLORS["line"])
        row = tk.Frame(self.mini, bg=COLORS["panel"])
        row.pack(fill="x", padx=12, pady=(10, 6))
        self.mini_state = tk.Label(row, text="TYPING", font=self.font_label,
                                   fg=COLORS["accent"], bg=COLORS["panel"])
        self.mini_state.pack(side="left")
        self.mini_percent = tk.Label(row, font=self.font_mono, fg=COLORS["text"],
                                     bg=COLORS["panel"])
        self.mini_percent.pack(side="right")
        self.progress_bar = tk.Canvas(self.mini, height=4, bg=COLORS["line"],
                                      highlightthickness=0)
        self.progress_bar.pack(fill="x", padx=12)
        self.progress_fill = self.progress_bar.create_rectangle(
            0, 0, 0, 4, fill=COLORS["accent"], width=0
        )
        self.mini_info = tk.Label(self.mini, text="", font=self.font_ui, fg=COLORS["dim"],
                                  bg=COLORS["panel"], anchor="w")
        self.mini_info.pack(fill="x", padx=12, pady=(6, 0))
        buttons = tk.Frame(self.mini, bg=COLORS["panel"])
        buttons.pack(fill="x", padx=12, pady=(6, 12))
        self.mini_pause = self._button(buttons, "Pause", self.toggle_pause,
                                       bg=COLORS["panel"])
        self.mini_pause.pack(side="left")
        self._button(buttons, "Stop", self.stop_typing).pack(side="right")

    def _wire_events(self):
        """Bind the events that need to fire after the widgets exist."""
        self.text_box.bind("<<Modified>>", self._on_text_modified)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll_job = self.root.after(EVENT_POLL_MS, self._drain_events)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _on_text_modified(self, _event=None):
        """Refresh the counters whenever the text changes."""
        self.refresh()
        self.text_box.edit_modified(False)

    def update(self):
        """Process pending UI events (used by tests and the worker thread)."""
        self.root.update()

    def current_text(self):
        """Text currently in the editor."""
        return self.text_box.get("1.0", "end-1c")

    def refresh(self):
        """Recompute the character/word counters and the ETA."""
        text = self.current_text()
        words = len(text.split())
        self.count_label.config(text=f"{len(text):,} CHARS · {words:,} WORDS")
        if not text:
            self.eta_label.config(text="")
            return
        seconds = estimate_seconds(text, self.slider_wpm.get(),
                                   self.slider_variation.get() / 100)
        self.eta_label.config(text=f"≈ {fmt_time(seconds)}")

    def persist(self):
        """Save the current settings and text to disk."""
        save_settings({
            "wpm": self.slider_wpm.get(),
            "variation": self.slider_variation.get(),
            "delay": self.slider_delay.get(),
            "text": self.current_text(),
        })

    def say(self, message, color=None):
        """Show a status message under the main view."""
        self.message_label.config(text=message, fg=color or COLORS["warn"])

    def clear_text(self):
        """Empty the text editor."""
        self.text_box.delete("1.0", "end")
        self.refresh()

    def open_file(self):
        """Load a .txt/.md file into the editor."""
        from tkinter import filedialog

        path = filedialog.askopenfilename(filetypes=TEXT_FILE_TYPES)
        if not path:
            return
        with open(path, encoding="utf-8", errors=DECODE_ERRORS) as handle:
            content = handle.read().replace("\r\n", "\n")
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", content)
        self.refresh()

    # ------------------------------------------------------------------
    # target picking
    # ------------------------------------------------------------------
    def pick(self):
        """Hide the app and let the user click the target text box."""
        self.pick_button.set(enabled=False)
        self.root.iconify()
        threading.Thread(target=self._wait_for_click, daemon=True).start()

    def _wait_for_click(self):
        """Block until the user clicks a spot (or cancels with Escape)."""
        time.sleep(PICK_ARM_DELAY)
        while self.backend.key_down(VK_LBUTTON):
            time.sleep(0.01)
        spot = None
        started = time.time()
        while time.time() - started < PICK_TIMEOUT_SECONDS:
            if self.backend.key_down(VK_ESCAPE):
                break
            if self.backend.key_down(VK_LBUTTON):
                spot = self.backend.cursor_pos()
                break
            time.sleep(0.01)
        self.events.put(("pick", spot))

    def _finish_pick(self, spot):
        """Restore the window and record the picked target."""
        self.root.deiconify()
        self.pick_button.set(enabled=True)
        if not spot:
            self.say("Pick cancelled.")
            return
        self.state["spot"] = spot
        self.state["hwnd"] = self.backend.root_window_at(*spot)
        title = _shorten_title(self.backend.window_title(self.state["hwnd"]))
        self.spot_label.config(text=f"{title}   ({spot[0]}, {spot[1]})", fg=COLORS["text"])
        self.spot_dot.config(fg=COLORS["accent"])
        self.say("")

    # ------------------------------------------------------------------
    # run / pause / stop
    # ------------------------------------------------------------------
    def toggle_pause(self):
        """Pause or resume the running session."""
        typist = self.state["typist"]
        if typist:
            typist.toggle()

    def stop_typing(self):
        """Stop the running session."""
        typist = self.state["typist"]
        if typist:
            typist.stop()

    def go(self):
        """Start a typing session."""
        text = self.current_text()
        if not text:
            return self.say("Enter some text first.")
        if not self.state["spot"]:
            return self.say("Pick a spot first.")
        self.persist()
        wpm = self.slider_wpm.get()
        variation = self.slider_variation.get() / 100
        delay = self.slider_delay.get()
        plan = plan_delays(text, wpm, variation)
        typist = Typist(self.backend, plan, target=self.state["hwnd"],
                        on_progress=self.ui_progress, on_state=self.ui_state)
        self.state["typist"] = typist
        self.go_button.set(enabled=False)
        self.show_mini()
        self.ui_progress(0, len(plan))
        threading.Thread(target=self._worker, args=(typist, delay), daemon=True).start()

    def _worker(self, typist, delay):
        """Background thread: count down, click the spot, then type."""
        try:
            if not self._countdown(typist, delay):
                return
            self.backend.click(*self.state["spot"])
            time.sleep(CLICK_SETTLE_DELAY)
            typist.target = self.backend.foreground()
            self.state["hwnd"] = typist.target
            typist.run()
        except Exception as exc:  # surfaced to the user in the UI
            self.ui_state(STATE_STOPPED, "0")
            self.events.put(("message", f"Error: {exc}", COLORS["bad"]))

    def _countdown(self, typist, delay):
        """Run the start delay; returns False if the user cancelled."""
        for number in range(delay, 0, -1):
            self.ui_state(STATE_COUNTDOWN, str(number))
            for _ in range(COUNTDOWN_TICKS):
                if self.backend.key_down(VK_ESCAPE) or typist.stopped:
                    typist.abort()
                    return False
                time.sleep(0.1)
        return True

    # ------------------------------------------------------------------
    # view switching
    # ------------------------------------------------------------------
    def show_mini(self):
        """Collapse the window into the floating control bar."""
        self.main_view.pack_forget()
        self.mini.pack(fill="both", expand=True)
        self.root.minsize(1, 1)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = screen_w - MINI_WIDTH - MINI_MARGIN
        y = screen_h - MINI_HEIGHT - MINI_BOTTOM_GAP
        spot_x, spot_y = self.state["spot"]
        if self._overlaps_spot(x, y, spot_x, spot_y):
            y = MINI_MARGIN
        self.root.geometry(f"{MINI_WIDTH}x{MINI_HEIGHT}+{x}+{y}")
        self.root.overrideredirect(True)

    def _overlaps_spot(self, x, y, spot_x, spot_y):
        """True if the mini bar would cover the target spot."""
        return (x - 10 <= spot_x <= x + MINI_WIDTH + 10
                and y - 40 <= spot_y <= y + MINI_HEIGHT + 10)

    def show_main(self):
        """Restore the full window."""
        self.root.overrideredirect(False)
        self.mini.pack_forget()
        self.main_view.pack(fill="both", expand=True)
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.go_button.set(enabled=True)

    # ------------------------------------------------------------------
    # engine callbacks (called from the worker thread)
    # ------------------------------------------------------------------
    def ui_state(self, state, info=""):
        """Reflect engine state changes in the UI (safe from any thread)."""
        self.events.put(("state", state, info))

    def _drain_events(self):
        """Apply queued worker-thread events on the Tk thread."""
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "state":
                self._apply_state(event[1], event[2])
            elif kind == "progress":
                self._apply_progress(event[1], event[2])
            elif kind == "message":
                self.say(event[1], event[2])
            elif kind == "pick":
                self._finish_pick(event[1])
        self.poll_job = self.root.after(EVENT_POLL_MS, self._drain_events)

    def _apply_state(self, state, info):
        """Apply a state change to the mini bar and status line."""
        if state == STATE_TYPING:
            self.mini_state.config(text="TYPING", fg=COLORS["accent"])
            self.mini_pause.set("Pause")
            self.mini_info.config(text="F9 pause · Esc stop")
        elif state == STATE_PAUSED:
            self.mini_state.config(text="PAUSED", fg=COLORS["warn"])
            self.mini_pause.set("Resume")
            self.mini_info.config(text=info + " · F9 resume")
        elif state == STATE_RESUMING:
            self.mini_state.config(text=f"RESUMING IN {info}", fg=COLORS["warn"])
            self.mini_info.config(text="Returning to your window…")
        elif state == STATE_COUNTDOWN:
            self.mini_state.config(text=f"STARTING IN {info}", fg=COLORS["dim"])
            self.mini_info.config(text="Esc to cancel")
        elif state in (STATE_DONE, STATE_STOPPED):
            self.show_main()
            self._report_finished(state, info)

    def _report_finished(self, state, info):
        """Show the final status line after a session ends."""
        if state == STATE_DONE:
            self.say("Done.", COLORS["accent"])
            return
        typed = info.replace("/", " of ")
        self.say(f"Stopped · {typed} characters typed.", COLORS["warn"])

    def ui_progress(self, index, total):
        """Update the progress bar and percentage (safe from any thread)."""
        self.events.put(("progress", index, total))

    def _apply_progress(self, index, total):
        """Redraw the progress bar."""
        width = self.progress_bar.winfo_width()
        self.progress_bar.coords(self.progress_fill, 0, 0, width * index / max(1, total), 4)
        self.mini_percent.config(text=f"{index * 100 // max(1, total)}%")

    def close(self):
        """Persist settings and exit cleanly."""
        self.persist()
        self.stop_typing()
        if self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None
        self.root.destroy()

    def run(self):
        """Enter the Tk event loop."""
        self.root.mainloop()


def run():
    """Launch the AutoTyper GUI."""
    if sys.platform != "win32":
        print("AutoTyper only runs on Windows.")
        return 1
    AutoTyperApp().run()
    return 0


__all__ = ["AutoTyperApp", "run"]
