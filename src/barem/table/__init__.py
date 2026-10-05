"""Table mode: turn command output into a readable, responsive table.

    df -h | barem
    ps aux | barem --sort -%mem --top 10

The single public entry point is `format_text`, which never raises: if the
input cannot be parsed it is returned unchanged with a note, because a
formatting tool must never be the reason an admin cannot read their disk
usage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import detect, layout, styles
from . import render as _render
from .humanize import sort_value
from .model import Table
from .theme import Theme, colors_available, unicode_available

__all__ = ["FORMATS", "STYLES", "Options", "format_text", "render_table"]

#: Border styles come from the registry; "cards" is the narrow-window layout.
STYLES = (*styles.border_names(), "cards")
BAR_STYLES = styles.bar_names()
FORMATS = ("md", "csv", "tsv", "json")

#: --where 'use% > 80', 'status ~ Exited', 'name != tmpfs'
_WHERE_RE = re.compile(r"^\s*([\w %:/.\-]+?)\s*(>=|<=|==|!=|~|>|<|=)\s*(.+?)\s*$")


@dataclass
class Options:
    """Everything the CLI can ask of table mode."""

    profile: str | None = None
    input_format: str | None = None
    #: Borders by default; see barem --styles for the alternatives.
    style: str = "dashes-grid"
    #: How percentages are drawn: blocks, shade, bracket, dots, line, pipes, number.
    bar_chars: str = "pipes"
    #: Spaces inside each cell, either side of the value.
    pad: int = 2
    #: Blank lines between two data rows.
    row_gap: int = 0
    #: Sit the table in the middle of the terminal.
    center: bool = True
    #: Wrap a value that does not fit rather than cutting it.
    wrap: bool = True
    export: str | None = None
    width: int | None = None
    max_width: int | None = None
    bars: bool = True
    bar_width: int = 20
    symbols: bool = False
    #: None means "leave it to the profile"; a number overrides it everywhere.
    warn: float | None = None
    crit: float | None = None
    color: bool | None = None
    unicode: bool = True
    summary: bool = True
    sort: str | None = None
    top: int | None = None
    columns: list[str] = field(default_factory=list)
    where: list[str] = field(default_factory=list)
    relative: bool = False
    no_header: bool = False
    raw: bool = False


def _theme(options: Options) -> Theme:
    use_color = colors_available() if options.color is None else options.color
    # Degrade cleanly: a terminal that cannot encode the blocks gets ASCII
    # rather than a UnicodeEncodeError part way through the table.
    use_unicode = options.unicode and unicode_available()
    forced = options.warn is not None or options.crit is not None
    border = styles.border(options.style, unicode_ok=use_unicode)
    bar = styles.bar_style(options.bar_chars, unicode_ok=use_unicode)
    return Theme(
        color=use_color and options.style not in FORMATS,
        unicode=use_unicode,
        symbols=options.symbols,
        warn=70.0 if options.warn is None else options.warn,
        crit=90.0 if options.crit is None else options.crit,
        force_thresholds=forced,
        bar_width=max(0, options.bar_width),
        bars=options.bars and options.bar_width > 0 and not bar.bare,
        border=border,
        bar_style=bar,
        pad=max(0, options.pad),
        row_gap=max(0, options.row_gap),
        center=options.center,
    )


def _resolve(table: Table, name: str):
    """Find a column by key or header, tolerating 'use%' for 'USE%'."""
    wanted = name.strip().lower().lstrip("-")
    for column in table.columns:
        if wanted in (column.key.lower(), column.header.lower()):
            return column
    # Allow a prefix, so --sort mem finds %MEM.
    for column in table.columns:
        if column.key.lower().startswith(wanted) or column.header.lower().startswith(wanted):
            return column
    for column in table.columns:
        if wanted in column.key.lower() or wanted in column.header.lower():
            return column
    return None


def _apply_where(table: Table, expressions: list[str]) -> list[str]:
    """Filter rows in place. Returns notes about anything unusable."""
    notes: list[str] = []
    for expression in expressions:
        match = _WHERE_RE.match(expression)
        if not match:
            notes.append(f"ignored filter {expression!r}: expected 'column > value'")
            continue
        name, op, wanted = match.groups()
        column = _resolve(table, name)
        if column is None:
            notes.append(f"ignored filter {expression!r}: no column {name.strip()!r}")
            continue
        table.rows = [
            row for row in table.rows if _keep(row.get(column.key, ""), op, wanted, column)
        ]
    return notes


def _keep(value: str, op: str, wanted: str, column) -> bool:
    """Whether one cell passes one comparison, by real value where possible."""
    if op == "~":
        try:
            return bool(re.search(wanted, value or "", re.IGNORECASE))
        except re.error:
            return wanted.lower() in (value or "").lower()

    left = sort_value(value, column.kind.value)
    right = sort_value(wanted, column.kind.value)
    # Compare numerically when both sides parsed as numbers, else as text.
    if left[0] == 0 and right[0] == 0:
        a, b = left[1], right[1]
    else:
        a, b = (value or "").strip().lower(), wanted.strip().lower()

    if op in ("==", "="):
        return a == b
    if op == "!=":
        return a != b
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    if op == ">=":
        return a >= b
    if op == "<=":
        return a <= b
    return True


def _apply_sort(table: Table, spec: str) -> list[str]:
    """Sort by a column's real value. A leading '-' means descending."""
    descending = spec.startswith("-")
    column = _resolve(table, spec)
    if column is None:
        return [f"ignored --sort {spec!r}: no such column"]
    table.rows.sort(
        key=lambda row: sort_value(row.get(column.key, ""), column.kind.value), reverse=descending
    )
    return []


def _apply_columns(table: Table, wanted: list[str]) -> list[str]:
    """Choose and order the columns, keeping the user's order."""
    chosen = []
    notes = []
    for name in wanted:
        column = _resolve(table, name)
        if column is None:
            notes.append(f"ignored column {name!r}: no such column")
        elif column not in chosen:
            chosen.append(column)
    if chosen:
        table.columns = chosen
    return notes


def format_text(text: str, options: Options | None = None) -> str:
    """Render command output as a table.

    Returns the input unchanged, with a note, if it cannot be parsed.
    """
    options = options or Options()
    if options.raw:
        return text.rstrip("\n")

    try:
        return _format(text, options)
    except Exception as error:  # fail soft, always
        note = f"barem: could not format input ({type(error).__name__})"
        return text.rstrip("\n") + "\n" + note


def _format(text: str, options: Options) -> str:
    if not text.strip():
        return ""

    table = detect.build_table(
        text,
        profile_name=options.profile,
        input_format=options.input_format,
        has_header=not options.no_header,
    )
    if table is None or not table.columns:
        return text.rstrip("\n")

    return render_table(table, options)


def render_table(table: Table, options: Options | None = None) -> str:
    """Render a Table that was built in memory rather than parsed from text.

    `barem help` assembles its results as a Table directly, so it gets the
    same borders, widths, colours and responsive layout as piped output.
    """
    options = options or Options()
    notes: list[str] = []
    filtered = False
    if options.where:
        notes += _apply_where(table, options.where)
        filtered = True
    if options.sort:
        notes += _apply_sort(table, options.sort)
    if options.top is not None and options.top >= 0:
        table.rows = table.rows[: options.top]
        filtered = True
    if options.columns:
        notes += _apply_columns(table, options.columns)
    if filtered:
        # The summary has to describe the rows actually shown, or --where
        # leaves a footer reporting totals the reader cannot see.
        table.recompute_summary()
    table.notes.extend(notes)

    theme = _theme(options)
    style = options.export or options.style
    width = layout.terminal_width(options.width, options.max_width)
    plan = _best_plan(table, theme, options, width)
    return _render.render(table, plan, theme, style=style, summary=options.summary)


def _plan_at(table, theme: Theme, options: Options, width: int, pad: int, bar: int, cells=None):
    """The layout this table gets at one padding and bar-length setting."""
    theme.pad, theme.bar_width = pad, bar
    cell_pad, sep, frame = theme.border.geometry(pad, layout.GAP)
    geom = layout.Geometry(cell_pad=cell_pad, sep=sep, frame=frame)
    return layout.plan(
        table,
        theme,
        width,
        force_cards=options.style == "cards",
        relative=options.relative,
        geom=geom,
        wrap_cells=options.wrap,
        cells=cells,
    )


def _concessions(plan) -> tuple[int, int, int]:
    """How much a layout had to give up, worst first.

    Cards cost the most, then every column dropped, then the bars going
    altogether. Padding and bar length are not in the tuple: they are what is
    being traded away to avoid the things that are.
    """
    return (int(plan.cards), len(plan.dropped), int(not plan.bars))


def _best_plan(table: Table, theme: Theme, options: Options, width: int):
    """Lay the table out, giving up decoration before giving up data.

    A long bar and a roomy cell are what make a wide table readable, but in a
    narrow window they cost whole columns. So both shrink before any data
    does: every setting is tried from the most generous down, the padding
    going first because two spaces a side across six columns buys more room
    than four cells of bar, and the layout that concedes least wins. The
    theme is left holding the winning settings, because the renderer has to
    draw exactly what the layout budgeted for.
    """
    asked_pad, asked_bar = theme.pad, theme.bar_width
    pads = list(range(asked_pad, 0, -1)) or [0]
    bars = [b for b in (asked_bar, 16, 12, 10, 8, 6) if 0 < b <= asked_bar] or [asked_bar]

    best, best_cost, chosen = None, None, (asked_pad, asked_bar)
    for bar in bars:
        # The cells depend on the bar length but not on the padding, so they
        # are built once here and reused across the padding attempts.
        theme.bar_width = bar
        cells = layout.build_cells(table, theme, options.relative)
        for pad in pads:
            trial = _plan_at(table, theme, options, width, pad, bar, cells=cells)
            cost = _concessions(trial)
            if best_cost is None or cost < best_cost:
                best, best_cost, chosen = trial, cost, (pad, bar)
            if best_cost == (0, 0, 0):
                break
        if best_cost == (0, 0, 0):
            break
    theme.pad, theme.bar_width = chosen
    return best


def profile_names() -> list[str]:
    """Names of every known profile, for --help and completion."""
    from .profiles import names

    return names()
