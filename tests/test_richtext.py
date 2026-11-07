"""Unit tests for formatted text: parsing pasted HTML and typing its styles."""

import random
import unittest

from autotyper.keys import FORMAT_BOLD, FORMAT_ITALIC, FORMAT_UNDERLINE
from autotyper.richtext import (
    Run,
    Style,
    format_keys,
    has_formatting,
    plain_text,
    runs_from_html,
    runs_from_spans,
    spans_from_runs,
)
from autotyper.typos import BACKSPACE, final_text, typo_settings

B, IT, U = Style.BOLD, Style.ITALIC, Style.UNDERLINE
PLAIN = Style.PLAIN

GOOGLE_DOCS = (
    '<meta charset="utf-8"><b style="font-weight:normal;" id="docs-internal-guid-6a1">'
    '<p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;">'
    '<span style="font-size:11pt;font-family:Arial;font-weight:400;font-style:normal;'
    'text-decoration:none;white-space:pre;white-space:pre-wrap;">Normal </span>'
    '<span style="font-size:11pt;font-weight:700;font-style:normal;text-decoration:none;'
    'white-space:pre-wrap;">bold</span>'
    '<span style="font-weight:400;font-style:italic;white-space:pre-wrap;"> italic</span>'
    '<span style="font-weight:400;text-decoration:underline;'
    'text-decoration-skip-ink:none;white-space:pre-wrap;"> under</span></p><br />'
    '<p dir="ltr"><span style="font-weight:400;white-space:pre-wrap;">Tab\there  two</span></p>'
    '</b><br class="Apple-interchange-newline">'
)

WORD = (
    "<html xmlns:o='urn:schemas-microsoft-com:office:office'><head>"
    "<meta charset=utf-8><style><!-- p.MsoNormal {margin:0in;} --></style></head>"
    "<body lang=EN-US><!--StartFragment--><p class=MsoNormal>Normal\r\n<b>bold</b> "
    "<i>italic</i> <u>under</u><o:p></o:p></p>\r\n"
    "<p class=MsoNormal><o:p>&nbsp;</o:p></p>\r\n"
    "<p class=MsoNormal>Tab<span style='mso-tab-count:1'>&nbsp;&nbsp;&nbsp; </span>after"
    "<o:p></o:p></p><!--EndFragment--></body></html>"
)

WORD_LIST = (
    "<p class=MsoListParagraph style='mso-list:l0 level1 lfo1'><![if !supportLists]>"
    "<span style='font-family:Symbol'><span style='mso-list:Ignore'>·<span "
    "style='font:7.0pt \"Times New Roman\"'>&nbsp;&nbsp;&nbsp; </span></span></span>"
    "<![endif]>Apples<o:p></o:p></p>"
    "<p class=MsoListParagraph style='mso-list:l1 level1 lfo2'><![if !supportLists]>"
    "<span><span style='mso-list:Ignore'>1.<span>&nbsp;&nbsp; </span></span></span>"
    "<![endif]>Pears<o:p></o:p></p>"
)


def styles(runs):
    return [(run.text, run.style) for run in runs]


class Parsing(unittest.TestCase):
    def test_plain_html_gives_one_plain_run(self):
        self.assertEqual(styles(runs_from_html("<p>Hello world</p>")), [("Hello world", PLAIN)])

    def test_bold_italic_and_underline_tags(self):
        runs = runs_from_html("a <b>b</b> <strong>s</strong> <i>i</i> <em>e</em> <u>u</u>")
        self.assertEqual(
            styles(runs),
            [
                ("a ", PLAIN),
                ("b", B),
                (" ", PLAIN),
                ("s", B),
                (" ", PLAIN),
                ("i", IT),
                (" ", PLAIN),
                ("e", IT),
                (" ", PLAIN),
                ("u", U),
            ],
        )

    def test_nested_styles_combine(self):
        runs = runs_from_html("<b>bold <i>both <u>all</u></i></b>")
        self.assertEqual(styles(runs), [("bold ", B), ("both ", B | IT), ("all", B | IT | U)])

    def test_css_weights_and_styles(self):
        html = (
            '<span style="font-weight:700">a</span><span style="font-weight: bold">b</span>'
            '<span style="font-weight:600">c</span><span style="font-weight:400">d</span>'
            '<span style="font-style:italic">e</span><span style="font-style:oblique">f</span>'
            '<span style="text-decoration: underline">g</span>'
            '<span style="text-decoration-line:underline">h</span>'
        )
        self.assertEqual(
            styles(runs_from_html(html)), [("abc", B), ("d", PLAIN), ("ef", IT), ("gh", U)]
        )

    def test_css_can_switch_a_tag_style_off(self):
        html = '<b style="font-weight:normal">plain <span style="font-weight:700">bold</span></b>'
        self.assertEqual(styles(runs_from_html(html)), [("plain ", PLAIN), ("bold", B)])

    def test_google_docs_formatting_and_spacing(self):
        runs = runs_from_html(GOOGLE_DOCS)
        self.assertEqual(plain_text(runs), "Normal bold italic under\n\nTab\there  two")
        self.assertEqual(
            styles(runs)[:4],
            [("Normal ", PLAIN), ("bold", B), (" italic", IT), (" under", U)],
        )

    def test_word_formatting_blank_line_and_tab(self):
        runs = runs_from_html(WORD)
        self.assertEqual(plain_text(runs), "Normal bold italic under\n\nTab\tafter")
        self.assertIn(("bold", B), styles(runs))
        self.assertIn(("italic", IT), styles(runs))
        self.assertIn(("under", U), styles(runs))

    def test_word_list_markers_become_bullets_and_numbers(self):
        self.assertEqual(plain_text(runs_from_html(WORD_LIST)), "• Apples\n1. Pears")

    def test_head_style_and_script_are_skipped(self):
        html = "<head><title>T</title><style>p{}</style></head><script>x()</script><p>Body</p>"
        self.assertEqual(plain_text(runs_from_html(html)), "Body")

    def test_whitespace_collapses_outside_preformatted_text(self):
        self.assertEqual(plain_text(runs_from_html("<p>  a \n  b\t\tc  </p>")), "a b c")

    def test_pre_keeps_every_space_tab_and_newline(self):
        self.assertEqual(plain_text(runs_from_html("<pre>a  b\n\tc</pre>")), "a  b\n\tc")

    def test_white_space_pre_wrap_style_keeps_spacing(self):
        html = '<span style="white-space:pre-wrap">a   b\tc</span>'
        self.assertEqual(plain_text(runs_from_html(html)), "a   b\tc")

    def test_paragraphs_and_line_breaks(self):
        html = "<p>one</p><p>two<br>three</p><div>four</div>"
        self.assertEqual(plain_text(runs_from_html(html)), "one\ntwo\nthree\nfour")

    def test_empty_paragraph_is_a_blank_line(self):
        html = "<p>one</p><p><br></p><p>two</p>"
        self.assertEqual(plain_text(runs_from_html(html)), "one\n\ntwo")

    def test_non_breaking_spaces_become_spaces(self):
        self.assertEqual(plain_text(runs_from_html("a&nbsp;&nbsp;b")), "a  b")

    def test_entities_are_decoded(self):
        html = "Tom &amp; Jerry &lt;3 caf&eacute;"
        self.assertEqual(plain_text(runs_from_html(html)), "Tom & Jerry <3 café")

    def test_unordered_list_items_get_bullets(self):
        html = "<p>Shopping:</p><ul><li>Milk</li><li><p>Eggs</p></li></ul>"
        self.assertEqual(plain_text(runs_from_html(html)), "Shopping:\n• Milk\n• Eggs")

    def test_ordered_list_items_are_numbered(self):
        html = "<ol><li>First</li><li>Second</li></ol>"
        self.assertEqual(plain_text(runs_from_html(html)), "1. First\n2. Second")

    def test_table_cells_are_separated_by_tabs(self):
        html = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"
        self.assertEqual(plain_text(runs_from_html(html)), "a\tb\nc\td")

    def test_headings_are_their_own_lines(self):
        html = "<h1>Title</h1><p>Body text</p>"
        self.assertEqual(plain_text(runs_from_html(html)), "Title\nBody text")

    def test_unclosed_and_stray_tags_do_not_break_parsing(self):
        self.assertEqual(plain_text(runs_from_html("</b>a<b>b</i>c")), "abc")

    def test_adjacent_runs_with_the_same_style_are_merged(self):
        runs = runs_from_html("<b>a</b><strong>b</strong>")
        self.assertEqual(styles(runs), [("ab", B)])

    def test_empty_html_gives_no_runs(self):
        self.assertEqual(runs_from_html(""), [])
        self.assertEqual(runs_from_html("<p></p><br>"), [])

    def test_carriage_returns_in_preformatted_text_become_newlines(self):
        html = '<span style="white-space:pre">a\r\nb\rc</span>'
        self.assertEqual(plain_text(runs_from_html(html)), "a\nb\nc")


class Helpers(unittest.TestCase):
    def test_has_formatting(self):
        self.assertFalse(has_formatting([Run("plain", PLAIN)]))
        self.assertTrue(has_formatting([Run("a", PLAIN), Run("b", IT)]))
        self.assertFalse(has_formatting([]))

    def test_spans_roundtrip(self):
        runs = [Run("ab", PLAIN), Run("cd", B | U), Run("e", IT)]
        spans = spans_from_runs(runs)
        self.assertEqual(spans, [[2, 4, (B | U).value], [4, 5, IT.value]])
        self.assertEqual(runs_from_spans("abcde", spans), runs)

    def test_spans_ignore_bad_entries(self):
        spans = [[0, 2, B.value], [3, 99, B.value], ["x", 1, 1], [1, 1, 1], [0, 1, 99], "junk"]
        self.assertEqual(runs_from_spans("abcd", spans), [Run("ab", B), Run("cd", PLAIN)])

    def test_overlapping_spans_combine(self):
        runs = runs_from_spans("abcd", [[0, 3, B.value], [2, 4, IT.value]])
        self.assertEqual(runs, [Run("ab", B), Run("c", B | IT), Run("d", IT)])


class FormatKeys(unittest.TestCase):
    def keys(self, runs, typos=None, seed=1):
        return format_keys(runs, typos, random.Random(seed))

    def test_plain_runs_need_no_shortcuts(self):
        self.assertEqual(self.keys([Run("hello", PLAIN)]), list("hello"))

    def test_styles_are_switched_on_and_off_around_their_text(self):
        keys = self.keys([Run("a ", PLAIN), Run("bold", B), Run(" z", PLAIN)])
        self.assertEqual(keys, [*"a ", FORMAT_BOLD, *"bold", FORMAT_BOLD, *" z"])

    def test_a_style_left_on_at_the_end_is_switched_off(self):
        keys = self.keys([Run("x", B | IT)])
        self.assertEqual(keys, [FORMAT_BOLD, FORMAT_ITALIC, "x", FORMAT_BOLD, FORMAT_ITALIC])

    def test_only_changed_styles_are_toggled(self):
        keys = self.keys([Run("a", B), Run("b", B | U), Run("c", U)])
        self.assertEqual(
            keys,
            [FORMAT_BOLD, "a", FORMAT_UNDERLINE, "b", FORMAT_BOLD, "c", FORMAT_UNDERLINE],
        )

    def test_final_text_ignores_shortcuts(self):
        keys = self.keys([Run("a ", PLAIN), Run("bold", B)])
        self.assertEqual(final_text(keys), "a bold")

    def test_typos_are_woven_in_and_still_give_the_exact_text(self):
        runs = [Run("plain words here ", PLAIN), Run("bold words here", B), Run(" end", PLAIN)]
        runs = runs * 30
        text = plain_text(runs)
        for seed in range(40):
            keys = self.keys(runs, typo_settings(10, 8), seed)
            self.assertEqual(final_text(keys), text)
            self.assertIn(BACKSPACE, keys)

    def test_a_fix_never_reaches_back_over_a_style_change(self):
        runs = [Run("ab", PLAIN), Run("cdefgh", B)] * 200
        for seed in range(20):
            field = []
            for key in self.keys(runs, typo_settings(10, 8), seed):
                if key != BACKSPACE:
                    field.append(key)
                    continue
                field.pop()
                self.assertNotEqual(field[-1:], [FORMAT_BOLD], "erased a run's first letter")


if __name__ == "__main__":
    unittest.main(verbosity=2)
