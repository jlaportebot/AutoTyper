"""Real X11 helpers shared by the integration tests (they need python-xlib and a display)."""

import threading
import time

from Xlib import X, Xatom, display
from Xlib.protocol import event

SERVE_SECONDS = 30.0
READY_TIMEOUT = 5.0
POLL_INTERVAL = 0.01


class HtmlClipboardOwner:
    """Owns the X11 CLIPBOARD and serves ``text/html`` as raw UTF-8, like a browser."""

    def __init__(self, html):
        self.data = html.encode("utf-8")
        self.display = display.Display()
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        if not self.ready.wait(READY_TIMEOUT):
            raise RuntimeError("the clipboard owner did not start")
        return self

    def __exit__(self, *_exc):
        self.stop_event.set()
        self.thread.join(READY_TIMEOUT)
        self.display.close()

    def _serve(self):
        x = self.display
        window = x.screen().root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
        names = ("CLIPBOARD", "TARGETS", "text/html")
        self.clipboard, self.targets, self.html = (x.intern_atom(name) for name in names)
        window.set_selection_owner(self.clipboard, X.CurrentTime)
        x.flush()
        self.ready.set()
        deadline = time.monotonic() + SERVE_SECONDS
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            while x.pending_events():
                self._answer(x.next_event())
            time.sleep(POLL_INTERVAL)

    def _answer(self, request):
        """Reply to one SelectionRequest with the targets list or the HTML bytes."""
        if request.type != X.SelectionRequest:
            return
        prop = request.property
        if request.target == self.targets:
            request.requestor.change_property(prop, Xatom.ATOM, 32, [self.targets, self.html])
        elif request.target == self.html:
            request.requestor.change_property(prop, self.html, 8, self.data)
        else:
            prop = X.NONE
        notify = event.SelectionNotify(
            time=request.time,
            requestor=request.requestor,
            selection=request.selection,
            target=request.target,
            property=prop,
        )
        request.requestor.send_event(notify)
        self.display.flush()
