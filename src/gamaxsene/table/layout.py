"""The responsive layout: measure, shrink, drop extras, drop columns, cards.

This is the core of table mode. The order of concessions matters, and it is
chosen so the most important information survives longest:

1. shrink the flexible text columns, widest first
2. drop the percentage bars, then the status symbols -- the numbers stay
3. drop whole columns, least important first
4. fall back to cards when even the essential columns will not fit

Numbers are never truncated, and the column that identifies the row is never
dropped.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

from .humanize import (
    human_duration,
    human_number,
    human_relative,
    human_size,
    parse_duration,
    parse_number,
    parse_percent,
    parse_size,
)
from .model import Column, Kind, Table, Trunc
from .theme import NEUTRAL, Theme, status_group
from .width import display_width, truncate

#: Below this the table is abandoned for cards; a table needs room for at
#: least an identity column and one value.
CARD_THRESHOLD = 50

#: Two spaces between columns reads better than a vertical line on every row.
GAP = 2

#: Percent cells are built from fixed-width parts so every row lines up:
#: bar, one space, then the number right-aligned. Four cells holds "  1%" to
#: "100%", but a decimal ("94.3%"), a value over 100 ("340%") or the critical
#: marker ("95%!") needs more, so the real width is measured per column.
PCT_NUMBER_WIDTH = 4


def terminal_width(explicit: int | None = None, max_width: int | None = None) -> int:
    """How many cells we may use.

    An explicit --width wins, then GAMAXSENE_WIDTH, then the real terminal.
    When stdout is redirected, get_terminal_size already falls back to 80,
    which is the right default for a file or another pipe.
    """
    width = explicit or 0
    if not width:
        try:
            width = int(os.environ.get("GAMAXSENE_WIDTH", 0))
        except ValueError:
            width = 0
    if not width:
        width = shutil.get_terminal_size(fallback=(80, 24)).columns
    width = max(width, 20)
    return min(width, max_width or 160)


@dataclass
class Cell:
    """One rendered cell: the text, plus how it should be painted."""

    text: str
    style: str = ""
    bar: str = ""
    bar_style: str = ""
    symbol: str = ""
    symbol_style: str = ""
    marker: str = ""  # "!" on a critical value when colour is unavailable


@dataclass
class Geometry:
    """How much space the chosen style spends on separators and borders.

    Fitting has to know this or the table overflows by exactly the width of
    its own decoration -- the bug the width invariant in the tests catches.
    """

    #: padding added inside every cell (the box style pads with a space each side)
    cell_pad: int = 0
    #: characters between two columns
    sep: int = GAP
    #: characters spent on the left and right edges together
    frame: int = 1

    def overhead(self, count: int) -> int:
        if count <= 0:
            return self.frame
        return self.cell_pad * count + self.sep * (count - 1) + self.frame


CLEAN_GEOMETRY = Geometry(cell_pad=0, sep=GAP, frame=1)
BOX_GEOMETRY = Geometry(cell_pad=2, sep=1, frame=2)


@dataclass
class Plan:
    """The decided layout for one table."""

    columns: list[Column]
    widths: dict[str, int]
    cells: list[dict[str, Cell]]
    bars: bool
    symbols: bool
    cards: bool = False
    dropped: list[Column] = field(default_factory=list)
    width: int = 80
    #: (number width, marker width) reserved inside each percent column.
    num_widths: dict[str, tuple[int, int]] = field(default_factory=dict)


# -- cell formatting ---------------------------------------------------------


def format_cell(column: Column, raw: str, theme: Theme, relative: bool = False) -> Cell:
    """Turn a raw string into a Cell, humanized and styled by kind."""
    value = (raw or "").strip()
    if not value or value == "-":
        return Cell(text=value)

    if column.kind is Kind.PERCENT:
        return _percent_cell(column, value, theme)
    if column.kind is Kind.SIZE:
        number = parse_size(value)
        return Cell(text=human_size(number) if number is not None else value)
    if column.kind is Kind.NUMBER:
        number = parse_number(value)
        return Cell(text=human_number(number) if number is not None else value)
    if column.kind is Kind.DURATION:
        seconds = parse_duration(value)
        if seconds is None:
            return Cell(text=value)
        return Cell(text=human_relative(seconds) if relative else human_duration(seconds))
    if column.kind is Kind.STATUS:
        group = status_group(value)
        style = {"good": "green", "busy": "yellow", "bad": "red"}.get(group, "")
        return Cell(
            text=value,
            style=style,
            symbol=theme.symbol(group) if group != NEUTRAL else "",
            symbol_style=style,
        )
    return Cell(text=value)


def _percent_cell(column: Column, value: str, theme: Theme) -> Cell:
    """A percentage, with its bar and its threshold colour.

    `ps` reports more than 100% CPU for a multi-threaded process, so the bar
    clamps at full while the number keeps the true value, in a colour that
    says it is not a disk-style percentage.
    """
    pct = parse_percent(value)
    if pct is None:
        return Cell(text=value)

    over = pct > 100
    level = theme.level(pct, column.warn, column.crit, column.invert)
    style = theme.level_style(level, over=over)
    text = f"{pct:.0f}%" if pct == int(pct) else f"{pct:.1f}%"
    marker = "!" if level == "bad" and not theme.color else ""
    return Cell(
        text=text,
        style=style,
        bar=theme.bar(min(pct, 100) / 100),
        bar_style=style,
        marker=marker,
    )


def build_cells(table: Table, theme: Theme, relative: bool = False) -> list[dict[str, Cell]]:
    return [
        {col.key: format_cell(col, row.get(col.key, ""), theme, relative) for col in table.columns}
        for row in table.rows
    ]


# -- measuring ---------------------------------------------------------------


def percent_number_widths(
    columns: list[Column], cells: list[dict[str, Cell]]
) -> dict[str, tuple[int, int]]:
    """Width of the number, and of the marker beside it, per percent column.

    Measured rather than assumed. Four cells holds "100%", but "94.3%" and
    "340%" do not fit, and getting this wrong overflows the table by exactly
    the difference. The marker gets a column of its own so that "95%!" and
    " 25%" still have their digits in the same place -- appending the "!" to
    the number would shift it one cell left.
    """
    widths: dict[str, tuple[int, int]] = {}
    for column in columns:
        if column.kind is not Kind.PERCENT:
            continue
        number = PCT_NUMBER_WIDTH
        marker = 0
        for row in cells:
            cell = row.get(column.key)
            if cell is not None and cell.bar:
                number = max(number, display_width(cell.text))
                marker = max(marker, display_width(cell.marker))
        widths[column.key] = (number, marker)
    return widths


def _cell_width(
    cell: Cell,
    column: Column,
    bars: bool,
    symbols: bool,
    num_width: tuple[int, int] = (PCT_NUMBER_WIDTH, 0),
) -> int:
    """How many cells this value needs, including its bar or symbol."""
    width = display_width(cell.text) + display_width(cell.marker)
    if column.kind is Kind.PERCENT and bars and cell.bar:
        number, marker = num_width
        return display_width(cell.bar) + 1 + number + marker
    if column.kind is Kind.STATUS and symbols and cell.symbol:
        width += display_width(cell.symbol) + 1
    return width


def natural_widths(
    columns: list[Column],
    cells: list[dict[str, Cell]],
    bars: bool,
    symbols: bool,
    num_widths: dict[str, tuple[int, int]] | None = None,
) -> dict[str, int]:
    """The width each column needs to show everything untruncated."""
    num_widths = num_widths or {}
    widths: dict[str, int] = {}
    for column in columns:
        widest = display_width(column.header)
        num_width = num_widths.get(column.key, (PCT_NUMBER_WIDTH, 0))
        for row in cells:
            cell = row.get(column.key)
            if cell is not None:
                widest = max(widest, _cell_width(cell, column, bars, symbols, num_width))
        if column.max_width:
            widest = min(widest, column.max_width)
        widths[column.key] = max(widest, 1)
    return widths


def _total(widths: dict[str, int], columns: list[Column], geom: Geometry = CLEAN_GEOMETRY) -> int:
    """Total rendered width, decoration included."""
    if not columns:
        return 0
    return sum(widths[c.key] for c in columns) + geom.overhead(len(columns))


# -- the algorithm -----------------------------------------------------------


def plan(
    table: Table,
    theme: Theme,
    width: int,
    force_cards: bool = False,
    relative: bool = False,
    geom: Geometry = CLEAN_GEOMETRY,
) -> Plan:
    """Decide the layout for this table at this width.

    The order of concessions is what makes the output stay useful: shrink
    text, then drop bars and symbols, then drop columns, then give up on a
    table altogether.
    """
    cells = build_cells(table, theme, relative)
    columns = list(table.columns)
    bars = theme.bars
    symbols = theme.symbols
    nums = percent_number_widths(columns, cells)

    def measure(cols, bars_, symbols_):
        return natural_widths(cols, cells, bars_, symbols_, nums)

    def done(cols, widths, bars_, symbols_, dropped=()):
        return Plan(
            cols,
            widths,
            cells,
            bars_,
            symbols_,
            dropped=list(dropped),
            width=width,
            num_widths=nums,
        )

    if force_cards or width < CARD_THRESHOLD:
        return Plan(
            columns,
            measure(columns, bars, symbols),
            cells,
            bars=bars,
            symbols=symbols,
            cards=True,
            width=width,
            num_widths=nums,
        )

    # 1-2. Measure, and print it as is if it already fits.
    widths = measure(columns, bars, symbols)
    if _total(widths, columns, geom) <= width:
        return done(columns, widths, bars, symbols)

    # 3. Shrink the flexible columns, widest first, so one long path does not
    #    starve every other column.
    widths = _shrink(columns, widths, width, geom)
    if _total(widths, columns, geom) <= width:
        return done(columns, widths, bars, symbols)

    # 4. Drop the cell extras: bars first, then status symbols. Numbers stay.
    for drop_bars, drop_symbols in ((True, False), (True, True)):
        if drop_bars and not bars and drop_symbols and not symbols:
            continue
        trial_bars = bars and not drop_bars
        trial_symbols = symbols and not drop_symbols
        widths = _shrink(columns, measure(columns, trial_bars, trial_symbols), width, geom)
        if _total(widths, columns, geom) <= width:
            return done(columns, widths, trial_bars, trial_symbols)
        bars, symbols = trial_bars, trial_symbols

    # 5. Drop whole columns, least important first.
    dropped: list[Column] = []
    kept = list(columns)
    while len(kept) > 1:
        candidate = _drop_candidate(kept)
        if candidate is None:
            break
        kept.remove(candidate)
        dropped.append(candidate)
        widths = _shrink(kept, measure(kept, bars, symbols), width, geom)
        if _total(widths, kept, geom) <= width:
            return done(kept, widths, bars, symbols, dropped)

    # 6. Even the essential columns will not fit: cards.
    return Plan(
        columns,
        measure(columns, theme.bars, theme.symbols),
        cells,
        bars=theme.bars,
        symbols=theme.symbols,
        cards=True,
        width=width,
        num_widths=nums,
    )


def _shrink(
    columns: list[Column], widths: dict[str, int], budget: int, geom: Geometry = CLEAN_GEOMETRY
) -> dict[str, int]:
    """Take width from the flexible columns until the table fits.

    Lowest priority first, and within that the widest column first, so the
    space comes off whatever has the most to spare.
    """
    widths = dict(widths)
    flexible = [c for c in columns if c.flexible and c.truncate is not Trunc.NONE]
    if not flexible:
        return widths

    excess = _total(widths, columns, geom) - budget
    # One cell at a time, re-choosing the victim each round, so the columns
    # shrink evenly instead of one collapsing to its minimum first. The loop
    # is bounded by the total width, so a few hundred iterations at most.
    while excess > 0:
        shrinkable = [c for c in flexible if widths[c.key] > c.min_width]
        if not shrinkable:
            break
        # Least important first; within that, whatever is widest has the most
        # to spare, so one long path never starves the rest.
        target = min(shrinkable, key=lambda c: (-c.priority, -widths[c.key]))
        widths[target.key] -= 1
        excess -= 1
    return widths


def _drop_candidate(columns: list[Column]) -> Column | None:
    """The next column to give up, or None if everything left is essential."""
    candidates = [c for c in columns if not c.identity and c.priority > 1]
    if not candidates:
        return None
    # Highest priority number goes first; ties broken by position from the right.
    return max(candidates, key=lambda c: (c.priority, columns.index(c)))


def fit_text(column: Column, text: str, width: int, theme: Theme) -> str:
    """Cut a value to its column width, in the way its kind calls for."""
    if display_width(text) <= width:
        return text
    if column.truncate is Trunc.NONE or column.numeric:
        return text  # numbers are never truncated; the layout pays elsewhere
    return truncate(text, width, middle=column.truncate is Trunc.MIDDLE, ellipsis=theme.ellipsis())
