"""Formatted text: runs of characters that share bold, italic and underline.

Pasted HTML (Google Docs, Word, LibreOffice, web pages) becomes a list of
:class:`Run` objects, keeping its paragraphs, blank lines, tabs and spacing.
``format_keys`` turns runs into the keys to press, switching styles with the
target editor's own shortcuts (Ctrl+B/I/U, Command on macOS). Fonts, sizes and
colours have no shortcut every editor shares, so they come from the target.

Pure functions only.
"""

import enum
import random
import re
from html.parser import HTMLParser
from typing import NamedTuple

from .keys import FORMAT_BOLD, FORMAT_ITALIC, FORMAT_UNDERLINE
from .typos import weave_typos


class Style(enum.Flag):
    """The character styles AutoTyper can reproduce."""

    PLAIN = 0
    BOLD = enum.auto()
    ITALIC = enum.auto()
    UNDERLINE = enum.auto()


ALL_STYLES = Style.BOLD | Style.ITALIC | Style.UNDERLINE
STYLE_KEYS = (
    (Style.BOLD, FORMAT_BOLD),
    (Style.ITALIC, FORMAT_ITALIC),
    (Style.UNDERLINE, FORMAT_UNDERLINE),
)


class Run(NamedTuple):
    """A stretch of text in one style."""

    text: str
    style: Style = Style.PLAIN


TAG_STYLES = {
    "b": Style.BOLD,
    "strong": Style.BOLD,
    "i": Style.ITALIC,
    "em": Style.ITALIC,
    "cite": Style.ITALIC,
    "dfn": Style.ITALIC,
    "var": Style.ITALIC,
    "u": Style.UNDERLINE,
    "ins": Style.UNDERLINE,
}
BLOCK_TAGS = frozenset(
    [
        "address",
        "article",
        "aside",
        "blockquote",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tr",
        "ul",
    ]
)
CELL_TAGS = frozenset(("td", "th"))
LIST_TAGS = frozenset(("ul", "ol"))
VOID_TAGS = frozenset(
    [
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    ]
)
HIDDEN_TAGS = frozenset(["head", "noscript", "script", "style", "template", "title", "xml"])
PREFORMATTED_TAGS = frozenset(("pre", "textarea"))
BOLD_WEIGHTS = frozenset(("bold", "bolder", "600", "700", "800", "900"))
ITALIC_STYLES = frozenset(("italic", "oblique"))
KEEP_SPACES = frozenset(("pre", "pre-wrap", "break-spaces"))
COLLAPSE_SPACES = frozenset(("normal", "nowrap", "pre-line"))
# Word draws list bullets with Symbol/Wingdings glyphs inside "mso-list:Ignore" spans.
WORD_BULLET_GLYPHS = frozenset(("·", "o", "§", "•", "▪", "-", "Ø", "ü"))
BULLET = "• "
COLLAPSIBLE_SPACE = re.compile(r"([ \t\n\r\f]+)")
NBSP = "\xa0"
APPLE_TRAILING_BREAK = "Apple-interchange-newline"


class _Frame(NamedTuple):
    """One open HTML element: the style and spacing rules inside it."""

    tag: str
    style: Style
    keeps_spaces: bool
    hidden: bool
    marker: bool


def _parse_css(declarations):
    """Inline CSS as a dict of lower-case ``name: value`` pairs (last one wins)."""
    css = {}
    for declaration in (declarations or "").split(";"):
        name, _, value = declaration.partition(":")
        if value.strip():
            css[name.strip().lower()] = value.strip().lower()
    return css


def _switched(style, flag, on):
    """``style`` with ``flag`` turned on or off."""
    return style | flag if on else style & ~flag


def _style_from_css(style, css):
    """Apply font-weight, font-style and text-decoration on top of ``style``."""
    if "font-weight" in css:
        style = _switched(style, Style.BOLD, css["font-weight"] in BOLD_WEIGHTS)
    if "font-style" in css:
        style = _switched(style, Style.ITALIC, css["font-style"] in ITALIC_STYLES)
    decoration = css.get("text-decoration-line", css.get("text-decoration"))
    if decoration is not None:
        style = _switched(style, Style.UNDERLINE, "underline" in decoration)
    return style


def _keeps_spaces(parent, tag, css):
    """Whether spaces, tabs and newlines inside this element are kept as typed."""
    white_space = css.get("white-space")
    if white_space in KEEP_SPACES:
        return True
    if white_space in COLLAPSE_SPACES:
        return False
    return parent.keeps_spaces or tag in PREFORMATTED_TAGS


class _RunBuilder(HTMLParser):
    """Walks the HTML and collects styled text the way a browser would show it."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = [_Frame("", Style.PLAIN, False, False, False)]
        self.pieces = []
        self.line_start = True
        self.pending_space = None
        self.lists = []
        self.marker_text = ""

    def _emit(self, text, style):
        """Append text, merging it into the previous piece when the style matches."""
        if self.pieces and self.pieces[-1][1] == style:
            self.pieces[-1][0] += text
        else:
            self.pieces.append([text, style])
        self.line_start = text.endswith("\n")

    def _flush_space(self):
        """Write a collapsed space that is waiting for more text on the line."""
        if self.pending_space is not None and not self.line_start:
            self._emit(" ", self.pending_space)
        self.pending_space = None

    def _trim_trailing_spaces(self):
        """Drop spaces at the end of the current line; nobody can see them."""
        while self.pieces and self.pieces[-1][0].endswith(" "):
            self.pieces[-1][0] = self.pieces[-1][0].rstrip(" ")
            if not self.pieces[-1][0]:
                self.pieces.pop()

    def _newline(self):
        """End the current line."""
        self.pending_space = None
        self._trim_trailing_spaces()
        self._emit("\n", Style.PLAIN)

    def _break_line(self):
        """Start a new line unless one has just started (block boundaries)."""
        if not self.line_start:
            self._newline()

    def _emit_marker(self, marker):
        """Write a list bullet or number; the item still counts as a fresh line."""
        self._break_line()
        self._emit(marker, Style.PLAIN)
        self.line_start = True

    def _list_marker(self):
        """The bullet or number for the next item of the innermost list."""
        if not self.lists or self.lists[-1] is None:
            return BULLET
        self.lists[-1] += 1
        return f"{self.lists[-1]}. "

    def _open_block(self, tag):
        """Line and cell boundaries that come before an element's content."""
        if tag in CELL_TAGS and not self.line_start:
            self.pending_space = None
            self._emit("\t", Style.PLAIN)
        elif tag == "li":
            self._emit_marker(self._list_marker())
        elif tag in BLOCK_TAGS:
            self._break_line()
        if tag in LIST_TAGS:
            self.lists.append(0 if tag == "ol" else None)

    def _frame_for(self, tag, attributes):
        """The style and spacing rules of a newly opened element."""
        parent = self.stack[-1]
        css = _parse_css(attributes.get("style"))
        style = _style_from_css(parent.style | TAG_STYLES.get(tag, Style.PLAIN), css)
        word_tab = "mso-tab-count" in css
        marker = parent.marker or css.get("mso-list") == "ignore"
        hidden = parent.hidden or tag in HIDDEN_TAGS or word_tab
        if word_tab and not parent.hidden:
            self._flush_space()
            self._emit("\t" * _tab_count(css["mso-tab-count"]), style)
        return _Frame(tag, style, _keeps_spaces(parent, tag, css), hidden, marker)

    def handle_starttag(self, tag, attrs):
        """Open an element: line breaks, list markers and inherited styles."""
        attributes = dict(attrs)
        if tag == "br":
            if APPLE_TRAILING_BREAK not in (attributes.get("class") or ""):
                self._newline()
            return
        self._open_block(tag)
        if tag in VOID_TAGS:
            return
        self.stack.append(self._frame_for(tag, attributes))

    def _close(self, frame):
        """Finish an element that is being closed."""
        if frame.marker and not self.stack[-1].marker:
            self._emit_word_marker()
        if frame.tag in LIST_TAGS and self.lists:
            self.lists.pop()
        if frame.tag in BLOCK_TAGS:
            self._break_line()

    def _emit_word_marker(self):
        """Turn a Word list marker ("·", "1.", "a)") into a bullet or number."""
        marker = self.marker_text.replace(NBSP, " ").strip()
        self.marker_text = ""
        if marker in WORD_BULLET_GLYPHS or not marker:
            self._emit_marker(BULLET)
        else:
            self._emit_marker(marker + " ")

    def handle_endtag(self, tag):
        """Close an element and anything left open inside it; ignore stray end tags."""
        if all(frame.tag != tag for frame in self.stack[1:]):
            return
        while True:
            frame = self.stack.pop()
            self._close(frame)
            if frame.tag == tag:
                return

    def handle_data(self, data):
        """Add text with the current element's style and spacing rules."""
        frame = self.stack[-1]
        if frame.marker:
            self.marker_text += data
        elif frame.keeps_spaces and not frame.hidden:
            self._add_preformatted(data, frame.style)
        elif not frame.hidden:
            self._add_collapsed(data, frame.style)

    def _add_preformatted(self, data, style):
        """Text whose spaces, tabs and line breaks are kept exactly."""
        data = data.replace("\r\n", "\n").replace("\r", "\n").replace(NBSP, " ")
        if data:
            self._flush_space()
            self._emit(data, style)

    def _add_collapsed(self, data, style):
        """Text whose runs of whitespace show as one space, as in a browser."""
        for piece in COLLAPSIBLE_SPACE.split(data):
            if not piece:
                continue
            if COLLAPSIBLE_SPACE.fullmatch(piece):
                if self.pending_space is None:
                    self.pending_space = style
                continue
            self._flush_space()
            self._emit(piece.replace(NBSP, " "), style)

    def runs(self):
        """The finished runs, without leading or trailing blank lines."""
        self._trim_trailing_spaces()
        text_runs = [Run(text, style) for text, style in self.pieces]
        return _strip_blank_lines(text_runs)


def _tab_count(value):
    """Number of tabs in a Word ``mso-tab-count`` value such as ``"1"``."""
    digits = re.match(r"\d+", value)
    return int(digits.group()) if digits else 1


def _strip_blank_lines(runs):
    """Remove newlines at the very start and end of the text."""
    text = plain_text(runs)
    start = len(text) - len(text.lstrip("\n"))
    end = len(text.rstrip("\n"))
    return slice_runs(runs, start, end)


def slice_runs(runs, start, end):
    """The runs covering characters ``start``..``end`` of their joined text."""
    sliced = []
    offset = 0
    for run in runs:
        piece = run.text[max(0, start - offset) : max(0, end - offset)]
        offset += len(run.text)
        if piece:
            sliced.append(Run(piece, run.style))
    return merge_runs(sliced)


def merge_runs(runs):
    """Join neighbouring runs that share a style and drop empty ones."""
    merged = []
    for run in runs:
        if not run.text:
            continue
        if merged and merged[-1].style == run.style:
            merged[-1] = Run(merged[-1].text + run.text, run.style)
        else:
            merged.append(run)
    return merged


def runs_from_html(html):
    """Styled runs for pasted HTML, laid out the way a browser would show it."""
    builder = _RunBuilder()
    builder.feed(html or "")
    builder.close()
    return builder.runs()


def plain_text(runs):
    """The text of ``runs`` without any styling."""
    return "".join(run.text for run in runs)


def has_formatting(runs):
    """True if any run is bold, italic or underlined."""
    return any(run.style != Style.PLAIN for run in runs)


def spans_from_runs(runs):
    """``[start, end, style value]`` for every styled run, for saving to settings."""
    spans = []
    offset = 0
    for run in runs:
        end = offset + len(run.text)
        if run.style != Style.PLAIN:
            spans.append([offset, end, run.style.value])
        offset = end
    return spans


def _valid_span(span, length):
    """``(start, end, Style)`` for a well-formed saved span, otherwise ``None``."""
    if not isinstance(span, (list, tuple)) or len(span) != 3:
        return None
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in span):
        return None
    start, end, value = span
    if not 0 <= start < end <= length or not 0 < value <= ALL_STYLES.value:
        return None
    return start, end, Style(value)


def runs_from_spans(text, spans):
    """Rebuild styled runs from plain ``text`` and saved spans, skipping bad spans."""
    styles = [Style.PLAIN] * len(text)
    for span in spans or ():
        valid = _valid_span(span, len(text))
        if valid is None:
            continue
        start, end, style = valid
        for index in range(start, end):
            styles[index] |= style
    return merge_runs([Run(char, style) for char, style in zip(text, styles)])


def _switch_keys(current, wanted):
    """Shortcut keys that change the editor from ``current`` to ``wanted`` style."""
    changed = current ^ wanted
    return [key for flag, key in STYLE_KEYS if changed & flag]


def format_keys(runs, typos=None, rng=None):
    """Keys to press for ``runs``: text, style shortcuts and (optionally) typos.

    Every style is switched off again at the end. A typo never falls on the first
    letter after a style change, so its fix never erases back across the change.
    """
    rng = rng or random.Random()
    keys = []
    current = Style.PLAIN
    for run in runs:
        switch = _switch_keys(current, run.style)
        keys.extend(switch)
        current = run.style
        if typos is None:
            keys.extend(run.text)
        else:
            keys.extend(weave_typos(run.text, typos, rng, first_slip=1 if switch else 0))
    keys.extend(_switch_keys(current, Style.PLAIN))
    return keys
