"""Measuring and cutting text by terminal cells, not by characters.

Every layout bug in a hand-written table renderer comes back to this module,
so it depends on nothing else and is tested first. Three rules:

- ANSI colour codes have zero width, so measuring happens on the plain string
  and colour is applied last, after padding.
- CJK characters and many emoji occupy two cells; combining marks occupy none.
- Control characters would shift the layout or inject escapes into the
  terminal, so they are replaced before anything is measured.
"""

from __future__ import annotations

import re
import unicodedata

ELLIPSIS = "…"
ASCII_ELLIPSIS = "~"

# CSI sequences (colour, cursor moves) and the shorter OSC/charset escapes.
ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")

# Zero-width characters that are not combining marks.
_ZERO_WIDTH = frozenset("​‌‍⁠﻿")


def strip_ansi(text: str) -> str:
    """The string as it appears on screen, with every escape sequence removed."""
    return ANSI_RE.sub("", text)


def char_width(char: str) -> int:
    """Terminal cells occupied by one character: 0, 1 or 2."""
    if char in _ZERO_WIDTH or unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 2
    return 1


def display_width(text: str) -> int:
    """Terminal cells occupied by a string, ignoring colour codes."""
    return sum(char_width(c) for c in strip_ansi(text))


def sanitize(text: str, tabsize: int = 8) -> str:
    """Make a value safe to lay out.

    Tabs are expanded, every other control character becomes a middle dot.
    A file name containing an escape sequence cannot then move the cursor or
    repaint part of the table.
    """
    text = text.expandtabs(tabsize)
    text = ANSI_RE.sub("", text)
    return "".join(c if c in ("\n",) or unicodedata.category(c)[0] != "C" else "·" for c in text)


def _slice_to_width(text: str, width: int) -> str:
    """The longest prefix of `text` that fits in `width` cells."""
    if width <= 0:
        return ""
    out: list[str] = []
    used = 0
    for char in text:
        w = char_width(char)
        if used + w > width:
            break
        out.append(char)
        used += w
    return "".join(out)


def _slice_tail(text: str, width: int) -> str:
    """The longest suffix of `text` that fits in `width` cells."""
    if width <= 0:
        return ""
    out: list[str] = []
    used = 0
    for char in reversed(text):
        w = char_width(char)
        if used + w > width:
            break
        out.append(char)
        used += w
    return "".join(reversed(out))


def truncate_end(text: str, width: int, ellipsis: str = ELLIPSIS) -> str:
    """Cut at the end: ``very long container nam…``."""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    mark = display_width(ellipsis)
    if width <= mark:
        return _slice_to_width(ellipsis, width)
    return _slice_to_width(text, width - mark) + ellipsis


def truncate_middle(text: str, width: int, ellipsis: str = ELLIPSIS) -> str:
    """Cut in the middle, keeping both ends: ``/var/lib/…/overlay2/diff``.

    Paths carry their meaning at both ends: the first segment says where it
    lives and the last says what it is.
    """
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    mark = display_width(ellipsis)
    if width <= mark:
        return _slice_to_width(ellipsis, width)
    room = width - mark
    # Favour the tail, which is usually the more identifying half.
    head = room // 2
    tail = room - head
    return _slice_to_width(text, head) + ellipsis + _slice_tail(text, tail)


def truncate(text: str, width: int, middle: bool = False, ellipsis: str = ELLIPSIS) -> str:
    """Cut `text` to `width`, at the end or in the middle."""
    return (truncate_middle if middle else truncate_end)(text, width, ellipsis)


def pad(text: str, width: int, align: str = "left") -> str:
    """Pad to `width` cells. Values wider than `width` are returned unchanged."""
    gap = width - display_width(text)
    if gap <= 0:
        return text
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap
