"""Human-like pacing maths for typed text.

Pure functions only: no I/O, no global state, fully deterministic when a
seeded ``random.Random`` is supplied.
"""

import random

from .keys import FORMAT_KEYS
from .typos import BACKSPACE, weave_typos

MIN_WPM = 5
MAX_WPM = 400
MAX_VARIATION = 0.9
CHARS_PER_WORD = 5
MIN_CHAR_DELAY = 0.005

SPACE_MULTIPLIER = 1.3
PAUSE_AFTER_COMMA = (2, 4)
PAUSE_AFTER_PERIOD = (4, 8)
PAUSE_AFTER_NEWLINE = (6, 12)
COMMA_CHARS = (",", ";", ":")
PERIOD_CHARS = (".", "!", "?")
# Correcting a slip: a beat to notice it, quick repeated backspaces, then a
# short hesitation before typing the right keys. Multiples of the base delay.
PAUSE_TO_NOTICE = (2.5, 6)
BACKSPACE_REPEAT = (0.45, 0.8)
PAUSE_AFTER_FIX = (1, 2.5)
# Reaching for Ctrl/Command plus a letter takes a little longer than one key.
PAUSE_FOR_SHORTCUT = (1, 2)


def clamp_wpm(wpm):
    """Clamp words-per-minute into the supported range."""
    return max(MIN_WPM, min(MAX_WPM, float(wpm)))


def clamp_variation(variation):
    """Clamp rhythm variation (0..0.9) into the supported range."""
    return max(0.0, min(MAX_VARIATION, float(variation)))


def base_delay(wpm):
    """Seconds between characters for a given words-per-minute rate."""
    return 60.0 / (clamp_wpm(wpm) * CHARS_PER_WORD)


def _correction_delay(previous, char, delay, base, rng):
    """Timing around a fix: notice the slip, erase quickly, then hesitate."""
    if char != BACKSPACE:
        return delay + base * rng.uniform(*PAUSE_AFTER_FIX)
    if previous == BACKSPACE:
        return base * rng.uniform(*BACKSPACE_REPEAT)
    return delay + base * rng.uniform(*PAUSE_TO_NOTICE)


def _adjust_delay(previous, char, delay, base, rng):
    """Apply the human rhythm rules that follow a character.

    A space stretches the next keystroke slightly; a comma, full stop or
    newline adds a longer, randomised pause; fixing a slip has its own timing.
    """
    if char in FORMAT_KEYS:
        return base * rng.uniform(*PAUSE_FOR_SHORTCUT)
    if BACKSPACE in (previous, char):
        return _correction_delay(previous, char, delay, base, rng)
    if previous == " ":
        return delay * SPACE_MULTIPLIER
    if previous in COMMA_CHARS:
        return delay + base * rng.uniform(*PAUSE_AFTER_COMMA)
    if previous in PERIOD_CHARS:
        return delay + base * rng.uniform(*PAUSE_AFTER_PERIOD)
    if previous == "\n":
        return delay + base * rng.uniform(*PAUSE_AFTER_NEWLINE)
    return delay


def plan_delays(text, wpm=60, variation=0.25, rng=None, typos=None):
    """Build the typing schedule.

    Returns a list of ``(character, delay_before_character_seconds)`` pairs.
    One "word" is five characters, matching the standard WPM convention.
    With ``typos`` (a :class:`~autotyper.typos.TypoSettings`) the schedule also
    contains slips and the backspaces that fix them.
    """
    rng = rng or random.Random()
    if typos is not None:
        text = weave_typos(text, typos, rng)
    return plan_keys(text, wpm, variation, rng)


def plan_keys(keys, wpm=60, variation=0.25, rng=None):
    """Build the typing schedule for an exact sequence of keys.

    ``keys`` holds characters, ``"\\b"`` backspaces and formatting shortcuts
    (``keys.FORMAT_KEYS``); returns ``(key, delay_before_key_seconds)`` pairs.
    """
    rng = rng or random.Random()
    base = base_delay(wpm)
    variation = clamp_variation(variation)
    plan = []
    previous = ""
    for char in keys:
        delay = base * rng.uniform(1 - variation, 1 + variation)
        delay = _adjust_delay(previous, char, delay, base, rng)
        plan.append((char, max(MIN_CHAR_DELAY, delay)))
        previous = char
    return plan


def estimate_seconds(text, wpm=60, variation=0.25, typos=None):
    """Estimate how long typing ``text`` takes, in seconds."""
    plan = plan_delays(text, wpm, variation, random.Random(0), typos)
    return sum(delay for _, delay in plan)


def fmt_time(seconds):
    """Format seconds as ``m:ss`` or ``h:mm:ss``."""
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
