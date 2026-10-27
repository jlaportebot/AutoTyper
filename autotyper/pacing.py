"""Human-like pacing maths for typed text.

Pure functions only: no I/O, no global state, fully deterministic when a
seeded ``random.Random`` is supplied.
"""

import random

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


def clamp_wpm(wpm):
    """Clamp words-per-minute into the supported range."""
    return max(MIN_WPM, min(MAX_WPM, float(wpm)))


def clamp_variation(variation):
    """Clamp rhythm variation (0..0.9) into the supported range."""
    return max(0.0, min(MAX_VARIATION, float(variation)))


def base_delay(wpm):
    """Seconds between characters for a given words-per-minute rate."""
    return 60.0 / (clamp_wpm(wpm) * CHARS_PER_WORD)


def _adjust_delay(previous, delay, base, rng):
    """Apply the human rhythm rules that follow a character.

    A space stretches the next keystroke slightly; a comma, full stop or
    newline adds a longer, randomised pause.
    """
    if previous == " ":
        return delay * SPACE_MULTIPLIER
    if previous in COMMA_CHARS:
        return delay + base * rng.uniform(*PAUSE_AFTER_COMMA)
    if previous in PERIOD_CHARS:
        return delay + base * rng.uniform(*PAUSE_AFTER_PERIOD)
    if previous == "\n":
        return delay + base * rng.uniform(*PAUSE_AFTER_NEWLINE)
    return delay


def plan_delays(text, wpm=60, variation=0.25, rng=None):
    """Build the typing schedule.

    Returns a list of ``(character, delay_before_character_seconds)`` pairs.
    One "word" is five characters, matching the standard WPM convention.
    """
    rng = rng or random.Random()
    base = base_delay(wpm)
    variation = clamp_variation(variation)
    plan = []
    previous = ""
    for char in text:
        delay = base * rng.uniform(1 - variation, 1 + variation)
        delay = _adjust_delay(previous, delay, base, rng)
        plan.append((char, max(MIN_CHAR_DELAY, delay)))
        previous = char
    return plan


def estimate_seconds(text, wpm=60, variation=0.25):
    """Estimate how long typing ``text`` takes, in seconds."""
    plan = plan_delays(text, wpm, variation, random.Random(0))
    return sum(delay for _, delay in plan)


def fmt_time(seconds):
    """Format seconds as ``m:ss`` or ``h:mm:ss``."""
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
