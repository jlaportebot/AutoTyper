"""The typing engine: walks a character plan and emits keystrokes.

The engine is platform independent. It talks to a backend that provides:

* ``type_char(ch)``      - type one character
* ``key_down(vk)``       - True while a physical key is held
* ``foreground()``       - handle of the focused window
* ``focus(hwnd)``        - bring a window back to the foreground
"""

import threading
import time

from .win_input import VK_ESCAPE, VK_F9

POLL_INTERVAL = 0.02
TICKS_PER_SECOND = 50
RESUME_REFOCUS_DELAY = 0.25
STATE_TYPING = "typing"
STATE_PAUSED = "paused"
STATE_RESUMING = "resuming"
RESULT_DONE = "done"
RESULT_STOPPED = "stopped"


class Typist:
    """Types a plan of ``(character, delay)`` pairs into a target window."""

    def __init__(self, backend, plan, target=None, on_progress=None, on_state=None,
                 resume_countdown=2, sleep=time.sleep):
        self.b = backend
        self.plan = plan
        self.target = target
        self.on_progress = on_progress or (lambda index, total: None)
        self.on_state = on_state or (lambda state, info="": None)
        self.resume_countdown = resume_countdown
        self.sleep = sleep
        self.pos = 0
        self._remaining = None  # seconds still to wait before the next char
        self._pause = threading.Event()
        self._resume = threading.Event()
        self._stop = threading.Event()
        self._f9_prev = False
        self.pause_reason = ""
        self.result = None

    def pause(self, reason="Paused"):
        """Pause typing, remembering why."""
        if not self._stop.is_set() and not self._pause.is_set():
            self.pause_reason = reason
            self._resume.clear()
            self._pause.set()

    def resume(self):
        """Request that a paused session continues."""
        if self._pause.is_set():
            self._resume.set()

    def toggle(self):
        """Pause if typing, resume if paused."""
        if self._pause.is_set():
            self.resume()
        else:
            self.pause()

    def stop(self):
        """Stop typing immediately."""
        self._stop.set()
        self._resume.set()

    def abort(self):
        """Cancel the session before any character is typed."""
        self.stop()
        self.result = RESULT_STOPPED
        self.on_state(RESULT_STOPPED, f"0/{len(self.plan)}")

    @property
    def paused(self):
        """True while the session is paused."""
        return self._pause.is_set()

    @property
    def stopped(self):
        """True once the session has been stopped."""
        return self._stop.is_set()

    def _f9_pressed(self):
        """True on the rising edge of the F9 key."""
        down = self.b.key_down(VK_F9)
        edge = down and not self._f9_prev
        self._f9_prev = down
        return edge

    def _esc(self):
        """True while the Escape key is held."""
        return self.b.key_down(VK_ESCAPE)

    def _wait(self):
        """Sleep off the current character's delay in small slices."""
        while self._remaining is not None and self._remaining > 0:
            if self._stop.is_set() or self._esc():
                self._stop.set()
                return False
            if self._f9_pressed():
                self.pause("Paused (F9)")
            if self._pause.is_set():
                return False
            step = min(POLL_INTERVAL, self._remaining)
            self.sleep(step)
            self._remaining -= step
        return True

    def _wait_for_resume(self):
        """Block until the user resumes; returns False if stopped."""
        self.on_state(STATE_PAUSED, self.pause_reason)
        while not self._resume.is_set():
            if self._stop.is_set() or self._esc():
                self._stop.set()
                return False
            if self._f9_pressed():
                self._resume.set()
                break
            self.sleep(POLL_INTERVAL)
        if self._stop.is_set():
            return False
        self._pause.clear()
        self._resume.clear()
        return self._countdown()

    def _countdown(self):
        """Count down before typing again so the user can switch windows."""
        for number in range(self.resume_countdown, 0, -1):
            self.on_state(STATE_RESUMING, str(number))
            for _ in range(TICKS_PER_SECOND):
                if self._stop.is_set() or self._esc():
                    self._stop.set()
                    return False
                if self._pause.is_set():
                    return True
                self.sleep(POLL_INTERVAL)
        if self.target is not None:
            self.b.focus(self.target)
            self.sleep(RESUME_REFOCUS_DELAY)
        self.on_state(STATE_TYPING, "")
        return True

    def run(self):
        """Type the whole plan; returns "done" or "stopped"."""
        self.on_state(STATE_TYPING, "")
        total = len(self.plan)
        while self.pos < total:
            if self._stop.is_set():
                break
            if self._pause.is_set():
                if not self._wait_for_resume():
                    break
                continue
            if not self._type_next():
                continue
        self.result = RESULT_DONE if self.pos >= total else RESULT_STOPPED
        self.on_state(self.result, f"{self.pos}/{total}")
        return self.result

    def _type_next(self):
        """Type the next character; returns False if typing was interrupted."""
        char, delay = self.plan[self.pos]
        if self._remaining is None:
            self._remaining = delay
        if not self._wait():
            return False
        if self.target is not None and self.b.foreground() != self.target:
            self.pause("Paused - you switched windows")
            return False
        self.b.type_char(char)
        self.pos += 1
        self._remaining = None
        self.on_progress(self.pos, len(self.plan))
        return True
