"""Human typing mistakes and how they get fixed.

``weave_typos`` turns the text to type into the key sequence a person would
really produce: every so often a slip (a neighbouring key, a doubled letter,
two swapped letters or a skipped letter), a few more keys typed before the
slip is noticed, then backspaces and the correct text.

Pure functions only: deterministic when a seeded ``random.Random`` is supplied.
"""

import random
from typing import NamedTuple

BACKSPACE = "\b"
CHARS_PER_WORD = 5
WORDS_PER_PERCENT = 100
MAX_TYPO_PERCENT = 10
MAX_CATCH_KEYS = 15
# A person who has just fixed a slip types the next few keys carefully.
MIN_KEYS_BETWEEN_SLIPS = 4

SLIP_SUBSTITUTE = "substitute"
SLIP_DOUBLE = "double"
SLIP_TRANSPOSE = "transpose"
SLIP_OMIT = "omit"
SLIP_KINDS = (SLIP_SUBSTITUTE, SLIP_DOUBLE, SLIP_TRANSPOSE, SLIP_OMIT)
# Hitting a neighbouring key is by far the most common slip.
SLIP_WEIGHTS = (55, 15, 15, 15)

QWERTY_LETTER_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
# Each row sits half a key to the right of the row above it.
NEIGHBOUR_OFFSETS = ((0, -1), (0, 1), (-1, 0), (-1, 1), (1, -1), (1, 0))
ASCII_PRINTABLE_FIRST = " "
ASCII_PRINTABLE_LAST = "~"


class TypoSettings(NamedTuple):
    """How often slips happen and how late they may be noticed."""

    percent: float = 0.0
    """Slips per 100 words (one word is five characters)."""
    catch_within: int = 0
    """Most correct keys typed after a slip before it is noticed."""

    @property
    def enabled(self):
        """True when any slips will be made."""
        return self.percent > 0


class Slip(NamedTuple):
    """One mistake: the keys typed instead of ``covers`` correct characters."""

    wrong: str
    covers: int


def typo_settings(percent, catch_within):
    """Build :class:`TypoSettings`, clamping both values into their ranges."""
    percent = max(0.0, min(float(MAX_TYPO_PERCENT), float(percent)))
    catch_within = max(0, min(MAX_CATCH_KEYS, int(catch_within)))
    return TypoSettings(percent, catch_within)


def _keys_around(rows, row_index, column):
    """Letters touching the key at ``rows[row_index][column]``."""
    around = []
    for row_step, column_step in NEIGHBOUR_OFFSETS:
        other_row = row_index + row_step
        other_column = column + column_step
        if 0 <= other_row < len(rows) and 0 <= other_column < len(rows[other_row]):
            around.append(rows[other_row][other_column])
    return "".join(around)


def _build_neighbours(rows):
    """Map every letter to the letters around it on the keyboard."""
    return {
        letter: _keys_around(rows, row_index, column)
        for row_index, row in enumerate(rows)
        for column, letter in enumerate(row)
    }


NEIGHBOURS = _build_neighbours(QWERTY_LETTER_ROWS)


def qwerty_neighbours(char):
    """Letters next to ``char`` on a QWERTY keyboard, in the same case."""
    around = NEIGHBOURS.get(char.lower(), "") if char.isascii() else ""
    return around.upper() if char.isupper() else around


def _is_slippable(char):
    """True for the characters a slip may land on: plain ASCII letters."""
    return bool(qwerty_neighbours(char))


def _is_plain(char):
    """True for printable ASCII, which one backspace always erases cleanly."""
    return ASCII_PRINTABLE_FIRST <= char <= ASCII_PRINTABLE_LAST


def final_text(keys):
    """The text left in a field after typing ``keys`` (backspaces erase)."""
    field = []
    for key in keys:
        if key != BACKSPACE:
            field.append(key)
        elif field:
            field.pop()
    return "".join(field)


def make_slip(text, index, rng, kind=None):
    """A slip on ``text[index]``; kinds that do not fit fall back to a wrong key."""
    kind = kind or rng.choices(SLIP_KINDS, SLIP_WEIGHTS)[0]
    char = text[index]
    following = text[index + 1] if index + 1 < len(text) else ""
    can_reach_next = _is_slippable(following)
    if kind == SLIP_DOUBLE:
        return Slip(char + char, 1)
    if kind == SLIP_TRANSPOSE and can_reach_next and following != char:
        return Slip(following + char, 2)
    if kind == SLIP_OMIT and can_reach_next:
        return Slip("", 1)
    return Slip(rng.choice(qwerty_neighbours(char)), 1)


def _catch_distance(catch_within, rng):
    """How many correct keys follow a slip before it is noticed (usually few)."""
    return min(catch_within, int(rng.triangular(0, catch_within + 1, 0)))


def _unnoticed_run(text, start, length):
    """Correct keys typed after a slip, stopping before anything hard to erase."""
    run = text[start : start + length]
    for offset, char in enumerate(run):
        if not _is_plain(char):
            return run[:offset]
    return run


def _mistake(text, index, catch_within, rng):
    """Keys for one slip and its fix, and how many characters of text they span."""
    slip = make_slip(text, index, rng)
    catch = _catch_distance(catch_within, rng)
    if not slip.wrong:
        catch = max(1, catch)
    run = _unnoticed_run(text, index + slip.covers, catch)
    typed = slip.wrong + run
    return typed + BACKSPACE * len(typed), slip.covers + len(run)


def _next_gap(mean_gap, rng):
    """Characters until the next slip; random, so slips never fall on a beat."""
    return int(rng.expovariate(1.0 / mean_gap))


def weave_typos(text, settings, rng=None):
    """Return the keys to press for ``text`` with slips and their fixes woven in."""
    if not settings.enabled:
        return text
    rng = rng or random.Random()
    mean_gap = WORDS_PER_PERCENT * CHARS_PER_WORD / settings.percent
    keys = []
    next_slip = _next_gap(mean_gap, rng)
    for index, char in enumerate(text):
        if index >= next_slip and _is_slippable(char):
            fix, span = _mistake(text, index, settings.catch_within, rng)
            keys.append(fix)
            next_slip = index + max(span + MIN_KEYS_BETWEEN_SLIPS, _next_gap(mean_gap, rng))
        keys.append(char)
    return "".join(keys)
