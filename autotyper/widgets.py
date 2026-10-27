"""Custom Tkinter widgets used by the AutoTyper UI."""

import tkinter as tk

from .gui_colors import COLORS


class Button(tk.Label):
    """A flat label styled as a button."""

    def __init__(self, master, text, command, kind="ghost", font=None, **kwargs):
        self.kind = kind
        self.command = command
        self.enabled = True
        super().__init__(master, text=text, font=font or "TkDefaultFont", padx=16, pady=7,
                         cursor="hand2", **kwargs)
        self._paint(False)
        self.bind("<Enter>", lambda _event: self._paint(True))
        self.bind("<Leave>", lambda _event: self._paint(False))
        self.bind("<Button-1>", lambda _event: self.enabled and self.command())

    def _paint(self, hover):
        """Repaint the button for its current state."""
        if not self.enabled:
            self.config(bg=COLORS["panel"], fg=COLORS["line"])
            return
        if self.kind == "primary":
            background = COLORS["accent"] if not hover else COLORS["accent_dk"]
            self.config(bg=background, fg="#0b0c0e")
        else:
            self.config(bg=COLORS["line"] if hover else COLORS["panel"], fg=COLORS["text"])

    def set(self, text=None, enabled=None, kind=None):
        """Update the label text, enabled flag, or button kind."""
        if text is not None:
            self.config(text=text)
        if enabled is not None:
            self.enabled = enabled
            self.config(cursor="hand2" if enabled else "arrow")
        if kind is not None:
            self.kind = kind
        self._paint(False)


class Slider(tk.Frame):
    """A labelled horizontal scale with a live value readout."""

    def __init__(self, master, label, low, high, value, unit="", on_change=None,
                 font_ui=None, font_label=None, font_mono=None):
        super().__init__(master, bg=COLORS["bg"])
        self.var = tk.IntVar(value=value)
        self.unit = unit
        self.on_change = on_change
        tk.Label(self, text=label, font=font_ui or "TkDefaultFont", fg=COLORS["text"],
                 bg=COLORS["bg"], width=14, anchor="w").pack(side="left")
        tk.Scale(self, from_=low, to=high, orient="horizontal", variable=self.var,
                 showvalue=False, bg=COLORS["bg"], troughcolor=COLORS["line"],
                 activebackground=COLORS["accent"], highlightthickness=0, bd=0,
                 sliderrelief="flat", sliderlength=14, width=6,
                 command=self._changed).pack(side="left", fill="x", expand=True, padx=8)
        self.value_label = tk.Label(self, font=font_mono or "TkFixedFont", fg=COLORS["accent"],
                                    bg=COLORS["bg"], width=7, anchor="e")
        self.value_label.pack(side="left")
        self.value_label.config(text=f"{value}{unit}")

    def _changed(self, *_args):
        """Update the readout and notify the owner."""
        self.value_label.config(text=f"{self.var.get()}{self.unit}")
        if self.on_change:
            self.on_change()

    def get(self):
        """Current slider value."""
        return self.var.get()

    def set(self, value):
        """Set the slider value and refresh the readout."""
        self.var.set(int(value))
        self.value_label.config(text=f"{self.var.get()}{self.unit}")
