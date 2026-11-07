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


if __name__ == "__main__":
    unittest.main(verbosity=2)
