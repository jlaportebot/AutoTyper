"""Unit tests for typing mistakes and their corrections."""

import random
import re
import unittest

from autotyper.typos import (
    BACKSPACE,
    MAX_CATCH_KEYS,
    MAX_TYPO_PERCENT,
    SLIP_DOUBLE,
    SLIP_OMIT,
    SLIP_SUBSTITUTE,
    SLIP_TRANSPOSE,
    Slip,
    TypoSettings,
    final_text,
    make_slip,
    qwerty_neighbours,
    typo_settings,
    weave_typos,
)

PROSE = (
    "The quick brown fox jumps over the lazy dog. Typing like a person means "
    "hitting the wrong key now and then, noticing a moment later, and fixing it.\n"
    "Second paragraph, with commas; colons: and a tab\there. "
)
LONG_PROSE = PROSE * 40
CORRECTION = re.compile("[^" + BACKSPACE + "]*?(" + BACKSPACE + "+)")


def weave(text, percent=5, catch=6, seed=1):
    return weave_typos(text, typo_settings(percent, catch), random.Random(seed))


def backspace_runs(keys):
    """Lengths of every run of consecutive backspaces."""
    return [len(run) for run in re.findall(BACKSPACE + "+", keys)]


def unnoticed_segments(keys):
    """The keys typed between the last correct state and each correction."""
    segments = []
    for match in re.finditer(BACKSPACE + "+", keys):
        count = len(match.group())
        segments.append(keys[match.start() - count : match.start()])
    return segments


class FinalText(unittest.TestCase):
    def test_backspace_removes_the_previous_character(self):
        self.assertEqual(final_text("helb" + BACKSPACE + "lo"), "hello")

    def test_backspace_on_an_empty_field_does_nothing(self):
        self.assertEqual(final_text(BACKSPACE * 3 + "ok"), "ok")

    def test_plain_text_is_unchanged(self):
        self.assertEqual(final_text("plain text\n"), "plain text\n")

    def test_accepts_any_iterable_of_keys(self):
        self.assertEqual(final_text(iter(["a", "x", BACKSPACE, "b"])), "ab")


class Settings(unittest.TestCase):
    def test_zero_percent_is_disabled(self):
        self.assertFalse(typo_settings(0, 6).enabled)

    def test_positive_percent_is_enabled(self):
        self.assertTrue(typo_settings(2, 0).enabled)

    def test_values_are_clamped_into_range(self):
        self.assertEqual(typo_settings(-5, -1), TypoSettings(0.0, 0))
        self.assertEqual(
            typo_settings(1000, 1000), TypoSettings(float(MAX_TYPO_PERCENT), MAX_CATCH_KEYS)
        )

    def test_default_settings_make_no_typos(self):
        self.assertFalse(TypoSettings().enabled)


class Neighbours(unittest.TestCase):
    def test_home_row_letter_has_its_qwerty_neighbours(self):
        self.assertEqual(set(qwerty_neighbours("s")), set("adwezx"))

    def test_corner_letter_has_only_real_neighbours(self):
        self.assertEqual(set(qwerty_neighbours("q")), set("wa"))

    def test_uppercase_letter_gets_uppercase_neighbours(self):
        self.assertEqual(set(qwerty_neighbours("S")), set("ADWEZX"))

    def test_non_letters_have_no_neighbours(self):
        for char in "1 .,\n\té😀":
            self.assertEqual(qwerty_neighbours(char), "", repr(char))

    def test_every_letter_has_at_least_two_neighbours(self):
        for letter in "abcdefghijklmnopqrstuvwxyz":
            self.assertGreaterEqual(len(qwerty_neighbours(letter)), 2, letter)


class MakeSlip(unittest.TestCase):
    def test_substitution_hits_a_neighbouring_key(self):
        slip = make_slip("hello", 2, random.Random(3), kind=SLIP_SUBSTITUTE)
        self.assertEqual(slip.covers, 1)
        self.assertIn(slip.wrong, qwerty_neighbours("l"))

    def test_substitution_keeps_the_case(self):
        slip = make_slip("Hello", 0, random.Random(3), kind=SLIP_SUBSTITUTE)
        self.assertIn(slip.wrong, qwerty_neighbours("H"))
        self.assertTrue(slip.wrong.isupper())

    def test_double_repeats_the_letter(self):
        self.assertEqual(make_slip("hello", 1, random.Random(1), kind=SLIP_DOUBLE), Slip("ee", 1))

    def test_transposition_swaps_two_letters(self):
        self.assertEqual(make_slip("the", 1, random.Random(1), kind=SLIP_TRANSPOSE), Slip("eh", 2))

    def test_transposition_of_identical_letters_falls_back_to_a_substitution(self):
        slip = make_slip("look", 1, random.Random(1), kind=SLIP_TRANSPOSE)
        self.assertEqual(slip.covers, 1)
        self.assertIn(slip.wrong, qwerty_neighbours("o"))

    def test_transposition_before_a_space_falls_back_to_a_substitution(self):
        slip = make_slip("ab c", 1, random.Random(1), kind=SLIP_TRANSPOSE)
        self.assertIn(slip.wrong, qwerty_neighbours("b"))

    def test_omission_skips_the_letter(self):
        self.assertEqual(make_slip("hello", 1, random.Random(1), kind=SLIP_OMIT), Slip("", 1))

    def test_omission_at_the_end_of_the_text_falls_back_to_a_substitution(self):
        slip = make_slip("ok", 1, random.Random(1), kind=SLIP_OMIT)
        self.assertIn(slip.wrong, qwerty_neighbours("k"))

    def test_omission_before_a_newline_falls_back_to_a_substitution(self):
        slip = make_slip("ok\nyes", 1, random.Random(1), kind=SLIP_OMIT)
        self.assertIn(slip.wrong, qwerty_neighbours("k"))

    def test_random_kinds_cover_every_slip_type(self):
        rng = random.Random(5)
        slips = {make_slip("there", 1, rng) for _ in range(400)}
        wrongs = {slip.wrong for slip in slips}
        self.assertIn("hh", wrongs)
        self.assertIn("eh", wrongs)
        self.assertIn("", wrongs)
        self.assertTrue(wrongs & set(qwerty_neighbours("h")))


class WeaveTypos(unittest.TestCase):
    def test_disabled_settings_return_the_text_unchanged(self):
        self.assertEqual(weave(PROSE, percent=0), PROSE)

    def test_result_always_corrects_back_to_the_original_text(self):
        texts = (PROSE, "a", "ab", "x\ny", "", "Tab\tthen\nnewline", "émoji 😀 中文 ok", "AAAA")
        for seed in range(200):
            for text in texts:
                keys = weave(text, percent=MAX_TYPO_PERCENT, catch=8, seed=seed)
                self.assertEqual(final_text(keys), text, (seed, text))

    def test_mistakes_are_actually_made(self):
        keys = weave(LONG_PROSE, percent=5)
        self.assertIn(BACKSPACE, keys)
        self.assertGreater(len(keys), len(LONG_PROSE))

    def test_deterministic_for_a_seeded_rng(self):
        self.assertEqual(weave(LONG_PROSE, seed=9), weave(LONG_PROSE, seed=9))

    def test_different_seeds_make_different_mistakes(self):
        self.assertNotEqual(weave(LONG_PROSE, seed=1), weave(LONG_PROSE, seed=2))

    def test_rate_tracks_the_requested_percentage_of_words(self):
        words = len(LONG_PROSE) / 5
        for percent in (2, 5, 10):
            counts = [len(backspace_runs(weave(LONG_PROSE, percent, seed=s))) for s in range(20)]
            rate = sum(counts) / len(counts) / words * 100
            self.assertTrue(0.6 * percent < rate < 1.25 * percent, (percent, rate))

    def test_higher_percentage_means_more_mistakes(self):
        few = len(backspace_runs(weave(LONG_PROSE, percent=1)))
        many = len(backspace_runs(weave(LONG_PROSE, percent=10)))
        self.assertGreater(many, few * 3)

    def test_distance_between_mistakes_varies(self):
        keys = weave(LONG_PROSE, percent=5, seed=4)
        starts = [match.start() for match in re.finditer(BACKSPACE + "+", keys)]
        gaps = {later - earlier for earlier, later in zip(starts, starts[1:])}
        self.assertGreater(len(gaps), 10)

    def test_catch_zero_fixes_every_slip_immediately(self):
        for seed in range(30):
            keys = weave(LONG_PROSE, percent=10, catch=0, seed=seed)
            self.assertLessEqual(max(backspace_runs(keys)), 2)

    def test_never_types_more_than_catch_keys_before_noticing(self):
        for catch in (1, 3, 6):
            for seed in range(30):
                keys = weave(LONG_PROSE, percent=10, catch=catch, seed=seed)
                self.assertLessEqual(max(backspace_runs(keys)), catch + 2, (catch, seed))

    def test_how_late_a_slip_is_noticed_varies(self):
        keys = weave(LONG_PROSE, percent=10, catch=8, seed=2)
        self.assertGreaterEqual(len(set(backspace_runs(keys))), 5)

    def test_a_late_catch_keeps_typing_past_the_slip(self):
        long_runs = [run for run in backspace_runs(weave(LONG_PROSE, 10, 8, seed=3)) if run >= 6]
        self.assertTrue(long_runs)

    def test_corrections_never_erase_a_newline_tab_or_non_ascii_character(self):
        text = ("Line one\tcolumn\nLine two é 😀 中文 done\n") * 60
        for seed in range(20):
            for segment in unnoticed_segments(weave(text, 10, 8, seed)):
                self.assertTrue(all(" " <= char <= "~" for char in segment), repr(segment))

    def test_text_without_ascii_letters_gets_no_mistakes(self):
        text = "1234 5678, 90! — 中文 😀 éèê\n" * 50
        self.assertEqual(weave(text, percent=MAX_TYPO_PERCENT), text)

    def test_wrong_keys_are_always_letters(self):
        for seed in range(20):
            keys = weave(LONG_PROSE, 10, 0, seed)
            for segment in unnoticed_segments(keys):
                self.assertTrue(segment.isalpha(), repr(segment))


if __name__ == "__main__":
    unittest.main(verbosity=2)
