"""Bold, italic and underline inside the Tk text editor.

Styles are kept as tags on the Text widget: one "meaning" tag per style, plus
font tags that only change how the text looks. All positions come from Tk itself
(never Python string offsets), because Tk counts an emoji as two characters.
"""

from typing import NamedTuple

from .richtext import Run, Style, merge_runs

SELECTION = "sel"
START = "1.0"
END = "end-1c"
STYLE_TAGS = {
    "fmt-bold": Style.BOLD,
    "fmt-italic": Style.ITALIC,
    "fmt-underline": Style.UNDERLINE,
}
TAG_FOR_STYLE = {style: tag for tag, style in STYLE_TAGS.items()}
FONT_STYLES = Style.BOLD | Style.ITALIC
FONT_TAGS = {
    Style.BOLD: ("font-bold", ("bold",)),
    Style.ITALIC: ("font-italic", ("italic",)),
    Style.BOLD | Style.ITALIC: ("font-bold-italic", ("bold", "italic")),
}


class Segment(NamedTuple):
    """A piece of the editor's text in one style, between two Tk indices."""

    text: str
    style: Style
    start: str
    end: str


class StyledText:
    """Reads and writes styled runs on a Tk Text widget."""

    def __init__(self, widget, family, size):
        self.widget = widget
        widget.tag_configure(TAG_FOR_STYLE[Style.UNDERLINE], underline=True)
        for tag, weights in FONT_TAGS.values():
            widget.tag_configure(tag, font=(family, size, *weights))

    def _style_at(self, index):
        """The style of the character at ``index``."""
        style = Style.PLAIN
        for tag in self.widget.tag_names(index):
            style |= STYLE_TAGS.get(tag, Style.PLAIN)
        return style

    def _segments(self, start=START, end=END):
        """Styled pieces of text between two indices, with their Tk positions."""
        items = self.widget.dump(start, end, text=True, tag=True)
        style = self._style_at(start)
        segments = []
        for position, (kind, value, index) in enumerate(items):
            if kind == "text":
                following = items[position + 1][2] if position + 1 < len(items) else end
                segments.append(Segment(value, style, index, following))
            elif value in STYLE_TAGS:
                flag = STYLE_TAGS[value]
                style = style | flag if kind == "tagon" else style & ~flag
        return segments

    def runs(self):
        """The whole text as styled runs."""
        return merge_runs([Run(piece.text, piece.style) for piece in self._segments()])

    def _tags_for(self, style):
        """The meaning tags for a style."""
        return tuple(tag for tag, flag in STYLE_TAGS.items() if style & flag)

    def insert_runs(self, runs, index="insert"):
        """Insert styled runs at ``index``."""
        for run in runs:
            self.widget.insert(index, run.text, self._tags_for(run.style))
        self.refresh_fonts()

    def set_runs(self, runs):
        """Replace the whole text with styled runs."""
        self.widget.delete(START, "end")
        self.insert_runs(runs, "end")

    def replace_selection(self, runs):
        """Put styled runs where the selection (or the cursor) is."""
        if self.widget.tag_ranges(SELECTION):
            start = self.widget.index("sel.first")
            self.widget.delete("sel.first", "sel.last")
            self.widget.mark_set("insert", start)
        self.insert_runs(runs)
        self.widget.see("insert")

    def toggle_style(self, flag):
        """Bold/italicise/underline the selection, or undo it if it is all styled already."""
        if not self.widget.tag_ranges(SELECTION):
            return
        selected = self._segments("sel.first", "sel.last")
        tag = TAG_FOR_STYLE[flag]
        if all(piece.style & flag for piece in selected):
            self.widget.tag_remove(tag, "sel.first", "sel.last")
        else:
            self.widget.tag_add(tag, "sel.first", "sel.last")
        self.refresh_fonts()

    def refresh_fonts(self):
        """Show bold and italic text in bold and italic fonts."""
        for tag, _weights in FONT_TAGS.values():
            self.widget.tag_remove(tag, START, "end")
        for piece in self._segments():
            font_style = piece.style & FONT_STYLES
            if font_style:
                self.widget.tag_add(FONT_TAGS[font_style][0], piece.start, piece.end)
