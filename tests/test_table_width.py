"""Tests for width.py, the foundation of the renderer.

Section 7 of the design calls these the first tests to write, because every
layout bug in a hand-written table renderer comes back to measuring text in
terminal cells rather than characters.
"""

import pytest

from barem.table.width import (
    display_width,
    pad,
    sanitize,
    strip_ansi,
    truncate_end,
    truncate_middle,
)

# --- measuring --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("abc", 3),
        ("/dev/sdb1", 9),
        ("█░", 2),  # block characters are single width
        ("你好", 4),  # CJK: two cells each
        ("こん", 4),  # hiragana is wide
        ("é", 1),  # e + combining acute is one cell
        ("a​b", 2),  # zero-width space adds nothing
        ("…", 1),  # the ellipsis we truncate with
    ],
)
def test_display_width(text, expected):
    assert display_width(text) == expected


def test_ansi_codes_have_no_width():
    plain = "95%"
    colored = "\033[1;31m95%\033[0m"
    assert display_width(colored) == display_width(plain) == 3


def test_strip_ansi_removes_every_escape():
    assert strip_ansi("\033[2mdim\033[0m") == "dim"
    assert strip_ansi("\033[38;5;214mx\033[0m") == "x"
    assert "\033" not in strip_ansi("\033]0;title\007body")


def test_sanitize_expands_tabs_and_neutralises_control_characters():
    assert "\t" not in sanitize("a\tb")
    # A file name carrying an escape sequence must not be able to move the
    # cursor or repaint part of the table.
    assert sanitize("evil\033[2Jname") == "evilname"
    assert sanitize("bell\x07") == "bell·"
    assert sanitize("cr\r") == "cr·"


def test_sanitized_text_measures_predictably():
    assert display_width(sanitize("a\tb")) == display_width("a       b")


# --- truncating -------------------------------------------------------------


def test_truncate_end_leaves_short_text_alone():
    assert truncate_end("abc", 10) == "abc"


def test_truncate_end_marks_the_cut():
    assert truncate_end("abcdefghij", 5) == "abcd…"
    assert display_width(truncate_end("abcdefghij", 5)) == 5


def test_truncate_middle_keeps_both_ends():
    out = truncate_middle("/var/lib/docker/overlay2/diff", 20)
    assert display_width(out) == 20
    assert out.startswith("/var")
    assert out.endswith("diff")
    assert "…" in out


@pytest.mark.parametrize("width", range(1, 30))
@pytest.mark.parametrize("middle", [False, True])
def test_truncation_never_exceeds_the_width(width, middle):
    text = "/var/lib/docker/overlay2/averylongdirectoryname/diff"
    cut = truncate_middle(text, width) if middle else truncate_end(text, width)
    assert display_width(cut) <= width


@pytest.mark.parametrize("width", range(1, 12))
def test_truncation_never_splits_a_wide_character(width):
    """Half of a CJK character would shift every following column."""
    cut = truncate_end("你好世界", width)
    assert display_width(cut) <= width


def test_truncate_to_nothing():
    assert truncate_end("abc", 0) == ""


# --- padding ----------------------------------------------------------------


def test_pad_left_right_and_centre():
    assert pad("ab", 5) == "ab   "
    assert pad("ab", 5, "right") == "   ab"
    assert pad("ab", 5, "center") == " ab  "


def test_pad_measures_in_cells_not_characters():
    assert display_width(pad("你", 5)) == 5


def test_pad_leaves_overlong_text_alone():
    assert pad("abcdef", 3) == "abcdef"
