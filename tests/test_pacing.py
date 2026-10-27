"""Unit tests for the human-like pacing maths."""

import random
import unittest

from autotyper.pacing import (
    CHARS_PER_WORD,
    base_delay,
    clamp_variation,
    clamp_wpm,
    estimate_seconds,
    fmt_time,
    plan_delays,
)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
