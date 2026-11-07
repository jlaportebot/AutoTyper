"""Unit tests for the human-like pacing maths."""

import random
import unittest

from autotyper.keys import FORMAT_BOLD, FORMAT_ITALIC
from autotyper.pacing import (
    CHARS_PER_WORD,
    base_delay,
    clamp_variation,
    clamp_wpm,
    estimate_seconds,
    fmt_time,
    plan_delays,
    plan_keys,
    rest_settings,
)
from autotyper.typos import BACKSPACE, final_text, typo_settings

PROSE = "the quick brown fox jumps over the lazy dog, then naps. " * 30


class Pacing(unittest.TestCase):
    def test_plan_covers_every_character_in_order(self):
        text = "Hello there.\nSecond line\twith tab"
        plan = plan_delays(text, 60, 0.25, random.Random(1))
        self.assertEqual([char for char, _ in plan], list(text))

    def test_plan_is_deterministic_for_a_seeded_rng(self):
        first = plan_delays("abc", 60, 0.25, random.Random(42))
        second = plan_delays("abc", 60, 0.25, random.Random(42))
        self.assertEqual(first, second)

    def test_zero_variation_gives_constant_delays(self):
        plan = plan_delays("abc", 60, 0.0, random.Random(7))
        delays = [delay for _, delay in plan]
        for delay in delays:
            self.assertAlmostEqual(delay, base_delay(60), places=6)

    def test_space_stretches_the_next_keystroke(self):
        plain = plan_delays("ab", 60, 0.0, random.Random(3))
        spaced = plan_delays("a b", 60, 0.0, random.Random(3))
        after_space = spaced[2][1]
        self.assertGreater(after_space, plain[1][1])
        self.assertAlmostEqual(after_space, base_delay(60) * 1.3, places=6)

    def test_sentence_end_pauses_longest(self):
        plan = plan_delays("a.\nb", 60, 0.0, random.Random(5))
        self.assertGreater(plan[2][1], plan[1][1])

    def test_wpm_is_clamped(self):
        self.assertEqual(clamp_wpm(1), 5)
        self.assertEqual(clamp_wpm(1000), 400)
        self.assertEqual(clamp_wpm(60), 60)

    def test_variation_is_clamped(self):
        self.assertEqual(clamp_variation(-1), 0.0)
        self.assertEqual(clamp_variation(5), 0.9)

    def test_slower_wpm_means_longer_time(self):
        text = "the quick brown fox jumps over the lazy dog"
        self.assertGreater(estimate_seconds(text, 30), estimate_seconds(text, 120))

    def test_estimate_matches_requested_wpm(self):
        text = "the quick brown fox jumps over the lazy dog " * 50
        for wpm in (30, 60, 120):
            actual = (len(text) / CHARS_PER_WORD) / (estimate_seconds(text, wpm, 0.25) / 60)
            self.assertTrue(0.6 * wpm < actual < 1.05 * wpm, (wpm, actual))

    def test_estimate_is_deterministic(self):
        text = "deterministic estimate"
        self.assertEqual(estimate_seconds(text, 70, 0.3), estimate_seconds(text, 70, 0.3))

    def test_fmt_time(self):
        self.assertEqual(fmt_time(65), "1:05")
        self.assertEqual(fmt_time(3725), "1:02:05")
        self.assertEqual(fmt_time(0), "0:00")

    def test_empty_text_produces_empty_plan(self):
        self.assertEqual(plan_delays("", 60, 0.25, random.Random(1)), [])


class PacingWithTypos(unittest.TestCase):
    def plan(self, text=PROSE, wpm=60, variation=0.0, seed=4, percent=10, catch=6):
        return plan_delays(text, wpm, variation, random.Random(seed), typo_settings(percent, catch))

    def test_typing_the_plan_leaves_exactly_the_text(self):
        for seed in range(40):
            plan = self.plan(variation=0.4, seed=seed)
            self.assertEqual(final_text(char for char, _ in plan), PROSE)

    def test_plan_contains_backspaces_when_typos_are_on(self):
        self.assertIn(BACKSPACE, [char for char, _ in self.plan()])

    def test_no_typos_by_default(self):
        plan = plan_delays(PROSE, 60, 0.25, random.Random(1))
        self.assertEqual("".join(char for char, _ in plan), PROSE)

    def test_zero_percent_matches_the_plain_plan(self):
        plain = plan_delays(PROSE, 60, 0.25, random.Random(1))
        self.assertEqual(self.plan(variation=0.25, seed=1, percent=0), plain)

    def first_backspaces(self, plan):
        return [
            delay
            for index, (char, delay) in enumerate(plan)
            if char == BACKSPACE and plan[index - 1][0] != BACKSPACE
        ]

    def test_noticing_a_slip_takes_a_moment(self):
        for delay in self.first_backspaces(self.plan()):
            self.assertGreater(delay, base_delay(60) * 2)

    def test_repeated_backspaces_are_quicker_than_typing(self):
        plan = self.plan(catch=10)
        repeats = [
            delay
            for index, (char, delay) in enumerate(plan)
            if char == BACKSPACE and plan[index - 1][0] == BACKSPACE
        ]
        self.assertTrue(repeats)
        for delay in repeats:
            self.assertLess(delay, base_delay(60))

    def test_retyping_after_a_fix_starts_with_a_short_hesitation(self):
        plan = self.plan()
        resumes = [
            delay
            for index, (char, delay) in enumerate(plan)
            if char != BACKSPACE and index and plan[index - 1][0] == BACKSPACE
        ]
        self.assertTrue(resumes)
        for delay in resumes:
            self.assertGreater(delay, base_delay(60))

    def test_typos_make_the_estimate_longer(self):
        without = estimate_seconds(PROSE, 60, 0.25)
        with_typos = estimate_seconds(PROSE, 60, 0.25, typo_settings(10, 8))
        self.assertGreater(with_typos, without * 1.05)

    def test_estimate_with_typos_is_deterministic(self):
        settings = typo_settings(5, 6)
        self.assertEqual(
            estimate_seconds(PROSE, 70, 0.3, settings), estimate_seconds(PROSE, 70, 0.3, settings)
        )


class PacingWithShortcuts(unittest.TestCase):
    KEYS = ["a", FORMAT_BOLD, "b", "c", FORMAT_BOLD, FORMAT_ITALIC, " ", "d", FORMAT_ITALIC]

    def test_plan_keeps_every_key_in_order(self):
        plan = plan_keys(self.KEYS, 60, 0.3, random.Random(2))
        self.assertEqual([key for key, _ in plan], self.KEYS)

    def test_reaching_for_a_shortcut_takes_a_little_longer(self):
        plan = plan_keys(self.KEYS, 60, 0.0, random.Random(2))
        for key, delay in plan:
            if key in (FORMAT_BOLD, FORMAT_ITALIC):
                self.assertGreaterEqual(delay, base_delay(60))

    def test_plain_text_keys_match_plan_delays(self):
        self.assertEqual(
            plan_keys(list("hello there."), 70, 0.3, random.Random(5)),
            plan_delays("hello there.", 70, 0.3, random.Random(5)),
        )


class PacingWithBreaks(unittest.TestCase):
    TEXT = "the quick brown fox jumps over the lazy dog. " * 40

    def plan(self, every, length, seed=1, **kwargs):
        rest = rest_settings(every, length)
        return plan_delays(self.TEXT, 60, 0.2, random.Random(seed), rest=rest, **kwargs)

    def total(self, plan):
        return sum(delay for _, delay in plan)

    def test_disabled_by_default_and_with_zero_interval(self):
        plain = plan_delays(self.TEXT, 60, 0.2, random.Random(1))
        self.assertEqual(self.plan(0, 5), plain)
        self.assertFalse(rest_settings(0, 5).enabled)
        self.assertTrue(rest_settings(10, 2).enabled)

    def test_values_are_clamped(self):
        self.assertEqual(rest_settings(-3, -1), rest_settings(0, 0))
        self.assertEqual(rest_settings(99999, 99999).every, rest_settings(3600, 600).every)

    def test_text_is_unchanged_by_breaks(self):
        plan = self.plan(10, 2)
        self.assertEqual("".join(key for key, _ in plan), self.TEXT)

    def test_a_break_roughly_every_interval(self):
        plan = self.plan(10, 3)
        long_pauses = [d for _, d in plan if d >= 2]
        expected = self.total(plan) / 13
        self.assertTrue(0.6 * expected <= len(long_pauses) <= 1.5 * expected + 1)

    def test_break_lengths_vary_around_the_setting(self):
        lengths = [d for _, d in self.plan(10, 3) if d >= 2]
        self.assertGreater(len(set(lengths)), 3)
        for length in lengths:
            self.assertTrue(2 <= length <= 6, length)

    def test_longer_interval_means_fewer_breaks(self):
        often = sum(1 for _, d in self.plan(5, 3) if d >= 2)
        rarely = sum(1 for _, d in self.plan(30, 3) if d >= 2)
        self.assertGreater(often, rarely)

    def test_estimate_includes_breaks(self):
        rest = rest_settings(10, 5)
        self.assertGreater(
            estimate_seconds(self.TEXT, 60, 0.2, rest=rest),
            estimate_seconds(self.TEXT, 60, 0.2) * 1.2,
        )

    def test_deterministic(self):
        self.assertEqual(self.plan(10, 2, seed=4), self.plan(10, 2, seed=4))

    def test_works_together_with_typos(self):
        plan = self.plan(10, 2, typos=typo_settings(10, 6))
        self.assertEqual(final_text(key for key, _ in plan), self.TEXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
