"""The border and percentage styles a table can be drawn in.

Both are registries rather than hard-coded characters, so a new look is a
dictionary entry and not a change to the renderer. `barem --styles` prints
them all with a sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# -- borders -----------------------------------------------------------------


@dataclass(frozen=True)
class Border:
    """Which lines a style draws, and what it draws them with."""

    name: str
    about: str
    #: corners and junctions, in reading order
    tl: str = ""
    tr: str = ""
    bl: str = ""
    br: str = ""
    h: str = ""
    v: str = ""
    lt: str = ""
    rt: str = ""
    tt: str = ""
    bt: str = ""
    x: str = ""
    #: a frame around the whole table
    outer: bool = True
    #: a line under the header row
    header_rule: bool = True
    #: a line between every pair of data rows
    row_rules: bool = False
    #: vertical lines between columns
    columns: bool = True
    #: usable without Unicode
    ascii_only: bool = False

    def geometry(self, pad: int, gap: int) -> tuple[int, int, int]:
        """(cell_pad, sep, frame) for the layout to budget with.

        Must match exactly what the renderer emits, or the table overflows by
        the width of its own decoration.

        - lines of any kind: every cell is padded on both sides, columns are
          separated by one character, and an outer frame costs two
        - no lines at all: no cell padding, the plain gap between columns, and
          a single space of left margin
        """
        if not self.columns and not self.outer:
            return 0, gap, 1
        return 2 * pad, (1 if self.columns else gap), (2 if self.outer else 0)


BOX = Border(
    "box",
    "square corners, a line under the header",
    tl="┌",
    tr="┐",
    bl="└",
    br="┘",
    h="─",
    v="│",
    lt="├",
    rt="┤",
    tt="┬",
    bt="┴",
    x="┼",
)

ROUNDED = Border(
    "rounded",
    "as box, with rounded corners",
    tl="╭",
    tr="╮",
    bl="╰",
    br="╯",
    h="─",
    v="│",
    lt="├",
    rt="┤",
    tt="┬",
    bt="┴",
    x="┼",
)

DOUBLE = Border(
    "double",
    "double lines, the heaviest look",
    tl="╔",
    tr="╗",
    bl="╚",
    br="╝",
    h="═",
    v="║",
    lt="╠",
    rt="╣",
    tt="╦",
    bt="╩",
    x="╬",
)

GRID = Border(
    "grid",
    "a line between every row, for tables you read across",
    tl="┌",
    tr="┐",
    bl="└",
    br="┘",
    h="─",
    v="│",
    lt="├",
    rt="┤",
    tt="┬",
    bt="┴",
    x="┼",
    row_rules=True,
)

DASHES = Border(
    "dashes",
    "plain +---+ and |, works on any terminal",
    tl="+",
    tr="+",
    bl="+",
    br="+",
    h="-",
    v="|",
    lt="+",
    rt="+",
    tt="+",
    bt="+",
    x="+",
    ascii_only=True,
)

DASHES_GRID = Border(
    "dashes-grid",
    "as dashes, with a line between every row",
    tl="+",
    tr="+",
    bl="+",
    br="+",
    h="-",
    v="|",
    lt="+",
    rt="+",
    tt="+",
    bt="+",
    x="+",
    row_rules=True,
    ascii_only=True,
)

SIMPLE = Border(
    "simple",
    "column lines and a header rule, no frame around the table",
    h="─",
    v="│",
    x="┼",
    lt="",
    rt="",
    outer=False,
)

CLEAN = Border(
    "clean",
    "no lines at all but a rule under the header",
    h="─",
    outer=False,
    columns=False,
)

MINIMAL = Border(
    "minimal",
    "nothing but aligned columns",
    outer=False,
    header_rule=False,
    columns=False,
)

BORDERS: dict[str, Border] = {
    b.name: b for b in (BOX, ROUNDED, DOUBLE, GRID, DASHES, DASHES_GRID, SIMPLE, CLEAN, MINIMAL)
}

#: What `--ascii` becomes, whatever style was asked for.
ASCII_EQUIVALENT = {
    "box": "dashes",
    "rounded": "dashes",
    "double": "dashes",
    "grid": "dashes-grid",
    "dashes": "dashes",
    "dashes-grid": "dashes-grid",
    "simple": "simple",
    "clean": "clean",
    "minimal": "minimal",
}


def border(name: str, unicode_ok: bool = True) -> Border:
    """Look a style up, falling back to its ASCII twin when needed."""
    style = BORDERS.get(name, BOX)
    if not unicode_ok:
        style = BORDERS[ASCII_EQUIVALENT.get(style.name, "dashes")]
        if style.name in ("simple", "clean", "minimal"):
            # these draw a rule and maybe a column line; swap them for ASCII
            style = Border(
                style.name,
                style.about,
                h="-",
                v="|" if style.columns else "",
                x="+",
                outer=style.outer,
                header_rule=style.header_rule,
                row_rules=style.row_rules,
                columns=style.columns,
                ascii_only=True,
            )
    return style


# -- percentages -------------------------------------------------------------


@dataclass(frozen=True)
class Bar:
    """How a percentage is drawn."""

    name: str
    about: str
    full: str = "█"
    #: partial glyphs from 1/8 to 7/8, for sub-cell precision; empty to skip
    partials: tuple[str, ...] = ()
    empty: str = "░"
    open_bracket: str = ""
    close_bracket: str = ""
    #: spaces between the bar and the number
    spacing: int = 2
    ascii_only: bool = False
    #: no bar at all, just the number
    bare: bool = False


BLOCKS = Bar(
    "blocks",
    "solid blocks, accurate to an eighth of a cell",
    full="█",
    partials=("▏", "▎", "▍", "▌", "▋", "▊", "▉"),
    empty="░",
)

SHADE = Bar(
    "shade",
    "a shaded track, quieter than solid blocks",
    full="▓",
    partials=("▒",),
    empty="░",
)

BRACKET = Bar(
    "bracket",
    "a bracketed meter, [####....]",
    full="#",
    empty=".",
    open_bracket="[",
    close_bracket="]",
    ascii_only=True,
)

DOTS = Bar(
    "dots",
    "filled and hollow dots",
    full="●",
    empty="○",
)

LINE = Bar(
    "line",
    "a simple rule, drawn and undrawn",
    full="━",
    empty="┄",
)

PIPES = Bar(
    "pipes",
    "upright pipes with nothing behind them",
    full="|",
    # A space, not a dot: the empty part of the bar is meant to be absent,
    # not drawn. The cell is still a fixed width, so the numbers line up.
    empty=" ",
    ascii_only=True,
)

TICKS = Bar(
    "ticks",
    "as pipes, on a dotted track",
    full="|",
    empty=".",
    ascii_only=True,
)

NUMBER = Bar("number", "the number on its own, no bar", bare=True)

BARS: dict[str, Bar] = {
    b.name: b for b in (PIPES, BLOCKS, SHADE, BRACKET, DOTS, LINE, TICKS, NUMBER)
}

ASCII_BAR = {
    "ticks": "ticks",
    "blocks": "bracket",
    "shade": "bracket",
    "dots": "bracket",
    "line": "pipes",
    "bracket": "bracket",
    "pipes": "pipes",
    "number": "number",
}


def bar_style(name: str, unicode_ok: bool = True) -> Bar:
    """Look a percentage style up, falling back to its ASCII twin if needed."""
    style = BARS.get(name, PIPES)
    if not unicode_ok and not style.ascii_only and not style.bare:
        style = BARS[ASCII_BAR.get(style.name, "bracket")]
    return style


# -- listing -----------------------------------------------------------------


@dataclass
class Sample:
    name: str
    about: str
    lines: list[str] = field(default_factory=list)


def border_names() -> list[str]:
    return list(BORDERS)


def bar_names() -> list[str]:
    return list(BARS)
