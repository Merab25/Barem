"""Turning a laid-out table into text.

Colour is applied last, after padding, because an escape sequence has zero
display width and padding a coloured string would be wrong by its length.
"""

from __future__ import annotations

import csv
import io
import json

from .layout import GAP, PCT_NUMBER_WIDTH, Cell, Plan, fit_text
from .model import Align, Kind, Table
from .theme import Theme
from .width import display_width, pad, truncate


def _align_of(column) -> str:
    """The pad() keyword for a column's alignment."""
    if column.align is Align.RIGHT:
        return "right"
    if column.align is Align.CENTER:
        return "center"
    return "left"


def _cell_text(cell: Cell, column, plan: Plan, theme: Theme, width: int) -> str:
    """One cell, padded to `width` and then painted."""
    if column.kind is Kind.PERCENT and plan.bars and cell.bar:
        # Three fixed-width parts -- bar, one space, number -- so the digits
        # start at the same column on every row.
        num_width, mark_width = plan.num_widths.get(column.key, (PCT_NUMBER_WIDTH, 0))
        number = pad(cell.text, num_width, "right") + pad(cell.marker, mark_width)
        bar_room = width - num_width - mark_width - 1
        bar = cell.bar if display_width(cell.bar) <= bar_room else cell.bar[: max(0, bar_room)]
        plain = f"{bar} {number}"
        painted = (
            f"{theme.paint(bar, cell.bar_style)} "
            f"{theme.paint(pad(cell.text, num_width, 'right'), cell.style)}"
            f"{pad(cell.marker, mark_width)}"
        )
        # Pad on the plain width, then emit the painted string.
        return " " * max(0, width - display_width(plain)) + painted

    text = cell.text + cell.marker
    if column.kind is Kind.STATUS and plan.symbols and cell.symbol:
        text = f"{cell.symbol} {cell.text}"
    text = fit_text(column, text, width, theme)
    padded = pad(text, width, _align_of(column))
    if not cell.style:
        return padded
    # Paint only the value, keeping the padding plain, so colour never bleeds.
    stripped = padded.strip()
    if not stripped:
        return padded
    start = padded.index(stripped[0])
    return padded[:start] + theme.paint(stripped, cell.style) + padded[start + len(stripped) :]


def render_clean(table: Table, plan: Plan, theme: Theme) -> str:
    """The default: no vertical lines, one light rule under the header."""
    columns, widths = plan.columns, plan.widths
    lines: list[str] = []

    # With --no-header there are no names, so the header row and its rule are
    # left out rather than printed blank.
    if any(column.header for column in columns):
        header_cells = []
        for column in columns:
            text = fit_text(column, column.header, widths[column.key], theme)
            header_cells.append(theme.header(pad(text, widths[column.key], _align_of(column))))
        lines.append(" " + (" " * GAP).join(header_cells).rstrip())

        rule_width = sum(widths[c.key] for c in columns) + GAP * (len(columns) - 1)
        lines.append(" " + theme.header(theme.rule_char() * min(rule_width, plan.width - 1)))

    for row in plan.cells:
        rendered = [
            _cell_text(row.get(c.key, Cell("")), c, plan, theme, widths[c.key]) for c in columns
        ]
        lines.append(" " + (" " * GAP).join(rendered).rstrip())

    return "\n".join(lines)


def render_box(table: Table, plan: Plan, theme: Theme) -> str:
    """Visible borders, for a screenshot or a ticket."""
    columns, widths = plan.columns, plan.widths
    box = theme.box_chars

    def rule(left: str, mid: str, right: str) -> str:
        return left + mid.join(box["h"] * (widths[c.key] + 2) for c in columns) + right

    lines = [rule(box["tl"], box["tt"], box["tr"])]

    header = []
    for column in columns:
        text = fit_text(column, column.header, widths[column.key], theme)
        header.append(" " + theme.header(pad(text, widths[column.key], _align_of(column))) + " ")
    lines.append(box["v"] + box["v"].join(header) + box["v"])
    lines.append(rule(box["lt"], box["x"], box["rt"]))

    for row in plan.cells:
        cells = [
            " " + _cell_text(row.get(c.key, Cell("")), c, plan, theme, widths[c.key]) + " "
            for c in columns
        ]
        lines.append(box["v"] + box["v"].join(cells) + box["v"])

    lines.append(rule(box["bl"], box["bt"], box["br"]))
    return "\n".join(lines)


def render_cards(table: Table, plan: Plan, theme: Theme) -> str:
    """One block per row, for a terminal too narrow for any table.

    The identity column becomes the heading, the rest become indented
    label/value pairs.
    """
    identity = table.identity_column()
    others = [c for c in plan.columns if c is not identity]
    label_width = max((display_width(c.header) for c in others), default=0)
    label_width = min(label_width, max(8, plan.width // 3))

    indent = 3
    blocks: list[str] = []
    for row in plan.cells:
        lines = []
        if identity is not None:
            head = row.get(identity.key, Cell("")).text or "-"
            lines.append(" " + theme.paint(fit_text(identity, head, plan.width - 2, theme), "bold"))
        for column in others:
            cell = row.get(column.key, Cell(""))
            if not cell.text:
                continue
            label = pad(
                truncate(column.header.title(), label_width, ellipsis=theme.ellipsis()), label_width
            )
            value = cell.text + cell.marker
            # Everything after the label, including the gap before it.
            room = plan.width - indent - label_width - 2
            bar = ""
            # The bar is the first thing to go when the card is narrow.
            if (
                column.kind is Kind.PERCENT
                and plan.bars
                and cell.bar
                and display_width(value) + 2 + display_width(cell.bar) <= room
            ):
                bar = cell.bar
            value = fit_text(
                column, value, max(1, room - (2 + display_width(bar) if bar else 0)), theme
            )
            painted = theme.paint(value, cell.style)
            if bar:
                painted = f"{painted}  {theme.paint(bar, cell.bar_style)}"
            lines.append(" " * indent + theme.header(label) + "  " + painted)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _md_align(column) -> str:
    """Markdown carries alignment in its separator row."""
    if column.align is Align.RIGHT:
        return "---:"
    if column.align is Align.CENTER:
        return ":---:"
    return "---"


def render_markdown(table: Table, plan: Plan, theme: Theme) -> str:
    """A GitHub-flavoured table, for pasting into an issue or a README."""
    columns = plan.columns
    head = "| " + " | ".join(c.header for c in columns) + " |"
    sep = "| " + " | ".join(_md_align(c) for c in columns) + " |"
    lines = [head, sep]
    for row in plan.cells:
        cells = []
        for column in columns:
            cell = row.get(column.key, Cell(""))
            text = (cell.text + cell.marker).replace("|", "\\|")
            cells.append(text)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_delimited(table: Table, plan: Plan, delimiter: str = ",") -> str:
    """CSV or TSV of the rendered values, for feeding another script."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    writer.writerow([c.header for c in plan.columns])
    for row in plan.cells:
        writer.writerow([row.get(c.key, Cell("")).text for c in plan.columns])
    return out.getvalue().rstrip("\n")


def render_json(table: Table, plan: Plan) -> str:
    """JSON array of objects, keyed by column key."""
    records = [{c.key: row.get(c.key, Cell("")).text for c in plan.columns} for row in plan.cells]
    return json.dumps(records, indent=2, ensure_ascii=False)


def render(
    table: Table, plan: Plan, theme: Theme, style: str = "clean", summary: bool = True
) -> str:
    """Render in the requested style, with the optional summary line."""
    if style == "md":
        return render_markdown(table, plan, theme)
    if style == "csv":
        return render_delimited(table, plan, ",")
    if style == "tsv":
        return render_delimited(table, plan, "\t")
    if style == "json":
        return render_json(table, plan)

    if plan.cards:
        body = render_cards(table, plan, theme)
    elif style in ("box", "ascii"):
        # Borders are the default, so the ASCII style is the same layout with
        # +---+ instead of the box-drawing characters.
        body = render_box(table, plan, theme)
    else:
        body = render_clean(table, plan, theme)

    parts = [body]
    extras: list[str] = []
    if plan.dropped:
        hidden = ", ".join(c.header.lower() for c in plan.dropped)
        extras.append(f"hidden: {hidden} (use --cols to force)")
    if summary and table.summary:
        extras.append(table.summary)
    extras.extend(table.notes)
    if extras:
        parts.append("")
        for extra in extras:
            if not theme.unicode:
                # The ASCII style must not smuggle a middle dot into the
                # footer of an otherwise plain-ASCII table.
                extra = extra.replace("·", "-")
            # The footer obeys the width budget too, or the invariant that no
            # line is wider than the terminal would fail on the summary alone.
            parts.append(
                " " + theme.header(truncate(extra, plan.width - 1, ellipsis=theme.ellipsis()))
            )
    return "\n".join(parts)
