"""Colours, thresholds, bar characters, and the ASCII fallback.

Colour is secondary information here: the number is always printed, and a
critical cell is also marked with `!` whenever colour is unavailable. The
output has to read the same in a log file, under NO_COLOR, and for a
colourblind reader.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from . import styles

# Eighth blocks give the bar about 1.25% precision, so 94% and 99% differ.
FULL_BLOCK = "█"
PARTIAL_BLOCKS = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉"]
EMPTY_BLOCK = "░"

ASCII_FULL = "#"
ASCII_EMPTY = "."

RULE = "─"
ASCII_RULE = "-"

BOX = {
    "tl": "┌",
    "tr": "┐",
    "bl": "└",
    "br": "┘",
    "h": "─",
    "v": "│",
    "lt": "├",
    "rt": "┤",
    "tt": "┬",
    "bt": "┴",
    "x": "┼",
}
ASCII_BOX = {
    "tl": "+",
    "tr": "+",
    "bl": "+",
    "br": "+",
    "h": "-",
    "v": "|",
    "lt": "+",
    "rt": "+",
    "tt": "+",
    "bt": "+",
    "x": "+",
}

#: Status words grouped by meaning, from section 5 of the design.
STATUS_GOOD = frozenset(
    {
        "up",
        "running",
        "active",
        "listen",
        "ready",
        "completed",
        "estab",
        "established",
        "succeeded",
        "healthy",
        "enabled",
        "online",
        "ok",
        "mounted",
        "available",
        "bound",
        "loaded",
        "synchronized",
        # the words `barem help` reports its own results with
        "pass",
        "passed",
        "clear",
    }
)
STATUS_BUSY = frozenset(
    {
        "pending",
        "containercreating",
        "restarting",
        "activating",
        "syn-sent",
        "syn-recv",
        "starting",
        "deactivating",
        "reloading",
        "waiting",
        "terminating",
        "podinitializing",
        "init",
        "time-wait",
        "close-wait",
        "degraded",
        "paused",
        "created",
        "warn",
        "warning",
        "watch",
    }
)
STATUS_BAD = frozenset(
    {
        "exited",
        "failed",
        "error",
        "crashloopbackoff",
        "inactive",
        "dead",
        "down",
        "unhealthy",
        "oomkilled",
        "evicted",
        "imagepullbackoff",
        "errimagepull",
        "notready",
        "unknown-state",
        "masked",
        "closed",
        "disabled",
        "offline",
        "lost",
        "stopped",
        "bad",
        "critical",
        "crit",
        "problem",
    }
)

GOOD, BUSY, BAD, NEUTRAL = "good", "busy", "bad", "neutral"

SYMBOLS = {GOOD: "●", BUSY: "◐", BAD: "✖", NEUTRAL: " "}
ASCII_SYMBOLS = {GOOD: "+", BUSY: "~", BAD: "x", NEUTRAL: " "}

_CODES = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    # Column names: bold and bright, because they are what the eye uses
    # to find its way around the table. The frame stays dim, so the
    # names and the data are what stand out.
    "head": "\033[1;96m",
    "magenta": "\033[35m",
    "bold_red": "\033[1;31m",
}


def status_group(value: str) -> str:
    """Which group a status word belongs to, or neutral if unknown."""
    text = (value or "").strip().lower()
    if not text:
        return NEUTRAL
    # Match on any word, so "Up 3 hours" and "Exited (0) 2 min ago" both work.
    words = {w.strip("(),.:") for w in text.replace("-", "-").split()}
    words.add(text)
    if words & STATUS_BAD:
        return BAD
    if words & STATUS_BUSY:
        return BUSY
    if words & STATUS_GOOD:
        return GOOD
    return NEUTRAL


def unicode_available() -> bool:
    """Whether stdout can actually encode the block and box characters.

    A terminal on a legacy code page would otherwise raise
    UnicodeEncodeError half way through a table, so the renderer falls back
    to the ASCII style instead of failing.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        (FULL_BLOCK + EMPTY_BLOCK + RULE + BOX["tl"] + "…").encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def colors_available(disabled: bool = False) -> bool:
    """Colour only on a real terminal, and never when NO_COLOR is set."""
    if disabled or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


@dataclass
class Theme:
    """Everything that depends on what the terminal can display."""

    color: bool = False
    unicode: bool = True
    symbols: bool = False
    warn: float = 70.0
    crit: float = 90.0
    bar_width: int = 12
    bars: bool = True
    #: border and percentage styles, from the styles registry
    border: styles.Border = field(default_factory=lambda: styles.BOX)
    bar_style: styles.Bar = field(default_factory=lambda: styles.BLOCKS)
    #: spaces inside each cell, either side of its value
    pad: int = 1
    #: blank lines between two data rows, for a table you read across
    row_gap: int = 0
    #: centre the whole table in the terminal rather than hugging the left
    center: bool = True
    #: the row-identifying column is emphasised so it stands out
    emphasise_identity: bool = True
    #: True when the user named thresholds on the command line, which then
    #: override a profile's per-column values. 90% full is critical for a disk
    #: but ordinary for a CPU, so profiles set their own -- until asked not to.
    force_thresholds: bool = False
    box_chars: dict = field(default_factory=lambda: dict(BOX))

    def __post_init__(self) -> None:
        if not self.unicode:
            self.box_chars = dict(ASCII_BOX)

    # -- painting ------------------------------------------------------------

    def paint(self, text: str, style: str) -> str:
        """Apply a style, or return the text unchanged when colour is off."""
        if not self.color or not style or style not in _CODES:
            return text
        return f"{_CODES[style]}{text}{_CODES['reset']}"

    def header(self, text: str) -> str:
        """A column name: bold and bright, so it is unmissable."""
        return self.paint(text, "head")

    def frame(self, text: str) -> str:
        """A border, a rule or the footer: quiet, so the data stands out."""
        return self.paint(text, "dim")

    def rule_char(self) -> str:
        return self.border.h or (RULE if self.unicode else ASCII_RULE)

    def ellipsis(self) -> str:
        return "…" if self.unicode else "~"

    def symbol(self, group: str) -> str:
        table = SYMBOLS if self.unicode else ASCII_SYMBOLS
        return table.get(group, " ")

    # -- thresholds ----------------------------------------------------------

    def level(
        self, pct: float, warn: float | None = None, crit: float | None = None, invert: bool = False
    ) -> str:
        """Which severity a percentage falls into.

        An inverted column (free space, available memory) is critical when the
        number is *low*, so the comparison flips.
        """
        if self.force_thresholds:
            warn, crit = self.warn, self.crit
        else:
            warn = self.warn if warn is None else warn
            crit = self.crit if crit is None else crit
        if invert:
            if pct <= 100 - crit:
                return BAD
            if pct <= 100 - warn:
                return BUSY
            return GOOD
        if pct >= crit:
            return BAD
        if pct >= warn:
            return BUSY
        return GOOD

    def level_style(self, level: str, over: bool = False) -> str:
        if over:
            return "magenta"  # above 100%, clearly not a disk-style percentage
        return {GOOD: "green", BUSY: "yellow", BAD: "bold_red"}.get(level, "")

    # -- bars ----------------------------------------------------------------

    def bar(self, fraction: float, width: int | None = None) -> str:
        """A fixed-width usage bar, accurate to about an eighth of a cell.

        The width never varies between rows, so the numbers beside the bars
        always start at the same column.
        """
        style = self.bar_style
        if style.bare:
            return ""
        width = self.bar_width if width is None else width
        if width <= 0:
            return ""
        fraction = max(0.0, min(1.0, fraction))

        exact = fraction * width
        full = int(exact)
        if full >= width:
            track = style.full * width
        elif style.partials:
            # Sub-cell precision, so 94% and 99% do not look identical.
            steps = len(style.partials) + 1
            index = int((exact - full) * steps)
            partial = style.partials[index - 1] if index else ""
            rest = width - full - (1 if partial else 0)
            track = style.full * full + partial + style.empty * max(0, rest)
        else:
            filled = round(fraction * width)
            track = style.full * filled + style.empty * (width - filled)
        return f"{style.open_bracket}{track}{style.close_bracket}"
