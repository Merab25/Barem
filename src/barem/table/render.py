"""Turning a laid-out table into text.

One engine draws every bordered style, driven by the Border spec rather than
by a branch per look, so a new style is a registry entry. Two rules hold
throughout:

- colour is applied last, after padding, because an escape sequence has zero
  display width and padding a coloured string would be wrong by its length
- a cell that does not fit is wrapped, not cut, so nothing is ever lost; only
  --no-wrap goes back to truncating
"""

from __future__ import annotations

import csv
import io
import json

from .layout import PCT_NUMBER_WIDTH, Cell, Plan, fit_text
from .model import Align, Kind, Table
from .theme import Theme
from .width import display_width, pad, truncate, wrap


def _align_of(column) -> str:
    """The pad() keyword for a column's alignment."""
    if column.align is Align.RIGHT:
        return "right"
    if column.align is Align.CENTER:
        return "center"
    return "left"


def _percent_text(cell: Cell, column, plan: Plan, theme: Theme, width: int) -> str:
    """A percentage: bar, spacing, number, marker -- all fixed width.

    The parts never vary between rows, so every number starts and ends in the
    same column however long the bar happens to be.
    """
    num_width, mark_width = plan.num_widths.get(column.key, (PCT_NUMBER_WIDTH, 0))
    gap = " " * theme.bar_style.spacing
    bar_room = width - num_width - mark_width - len(gap)
    bar = cell.bar if display_width(cell.bar) <= bar_room else cell.bar[: max(0, bar_room)]

    plain = f"{bar}{gap}{pad(cell.text, num_width, 'right')}{pad(cell.marker, mark_width)}"
    painted = (
        f"{theme.paint(bar, cell.bar_style)}{gap}"
        f"{theme.paint(pad(cell.text, num_width, 'right'), cell.style)}"
        f"{pad(cell.marker, mark_width)}"
    )
    return " " * max(0, width - display_width(plain)) + painted


def cell_lines(cell: Cell, column, plan: Plan, theme: Theme, width: int) -> list[str]:
    """One cell as the physical lines it occupies, padded and painted."""
    if column.kind is Kind.PERCENT and plan.bars and cell.bar:
        return [_percent_text(cell, column, plan, theme, width)]

    text = cell.text + cell.marker
    if column.kind is Kind.STATUS and plan.symbols and cell.symbol:
        text = f"{cell.symbol} {cell.text}"

    # Numbers are never wrapped or cut: the layout gives them their full width.
    if plan.wrap and not column.numeric and display_width(text) > width:
        pieces = wrap(text, width)
    else:
        pieces = [fit_text(column, text, width, theme)]

    style = cell.style
    if column.identity and theme.emphasise_identity:
        # The column that names the row is what the eye looks for first.
        style = style or "bold"
    return [_paint_padded(piece, width, _align_of(column), style, theme) for piece in pieces]


def _paint_padded(text: str, width: int, align: str, style: str, theme: Theme) -> str:
    """Pad to width, then colour only the value so padding stays plain."""
    padded = pad(text, width, align)
    if not style:
        return padded
    stripped = padded.strip()
    if not stripped:
        return padded
    start = padded.index(stripped[0])
    return padded[:start] + theme.paint(stripped, style) + padded[start + len(stripped) :]


def _header_lines(plan: Plan, theme: Theme) -> list[list[str]]:
    """The header cells, wrapped the same way the data is."""
    out = []
    for column in plan.columns:
        width = plan.widths[column.key]
        text = column.header

        if column.kind is Kind.PERCENT and plan.bars:
            # Sit the header over the number rather than at the cell edge,
            # since the marker column after it would otherwise push the two
            # a cell apart.
            num_width, mark_width = plan.num_widths.get(column.key, (PCT_NUMBER_WIDTH, 0))
            body = pad(text, max(num_width, display_width(text)), "right")
            out.append([theme.header(pad(body + " " * mark_width, width, "right"))])
            continue

        pieces = (
            wrap(text, width)
            if plan.wrap and display_width(text) > width
            else [fit_text(column, text, width, theme)]
        )
        out.append([theme.header(pad(piece, width, _align_of(column))) for piece in pieces])
    return out


def render_bordered(table: Table, plan: Plan, theme: Theme) -> str:
    """Draw the table in whatever border style the theme carries."""
    border = theme.border
    columns, widths = plan.columns, plan.widths
    cell_pad = " " * (theme.pad if (border.columns or border.outer) else 0)
    show_header = any(column.header for column in columns)

    def rule(left: str, mid: str, right: str) -> str:
        span = [border.h * (widths[c.key] + 2 * len(cell_pad)) for c in columns]
        if border.columns or border.outer:
            return left + mid.join(span) + right
        total = sum(widths[c.key] for c in columns) + plan.gap * (len(columns) - 1)
        return " " + theme.header(border.h * min(total, plan.width - 1))

    def body(cells: list[str]) -> str:
        if border.columns or border.outer:
            edge = border.v if border.outer else ""
            joined = border.v.join(f"{cell_pad}{c}{cell_pad}" for c in cells)
            return f"{edge}{joined}{edge}"
        return " " + (" " * plan.gap).join(cells).rstrip()

    def block(stack: list[list[str]]) -> list[str]:
        """One logical row, which may be several physical lines."""
        height = max(len(lines) for lines in stack) if stack else 1
        out = []
        for index in range(height):
            cells = []
            for column, lines in zip(columns, stack):
                cells.append(lines[index] if index < len(lines) else " " * widths[column.key])
            out.append(body(cells))
        return out

    lines: list[str] = []
    if border.outer:
        lines.append(theme.header(rule(border.tl, border.tt, border.tr)))

    if show_header:
        lines.extend(block(_header_lines(plan, theme)))
        if border.header_rule:
            lines.append(
                theme.header(rule(border.lt, border.x, border.rt))
                if (border.columns or border.outer)
                else rule("", "", "")
            )

    for position, row in enumerate(plan.cells):
        if border.row_rules and position:
            lines.append(theme.header(rule(border.lt, border.x, border.rt)))
        stack = [
            cell_lines(row.get(c.key, Cell("")), c, plan, theme, widths[c.key]) for c in columns
        ]
        lines.extend(block(stack))

    if border.outer:
        lines.append(theme.header(rule(border.bl, border.bt, border.br)))
    return "\n".join(lines)


def render_cards(table: Table, plan: Plan, theme: Theme) -> str:
    """One block per row, for a terminal too narrow for any table."""
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
            for piece in wrap(head, plan.width - 2):
                lines.append(" " + theme.paint(piece, "bold"))
        for column in others:
            cell = row.get(column.key, Cell(""))
            if not cell.text:
                continue
            label = pad(
                truncate(column.header.title(), label_width, ellipsis=theme.ellipsis()),
                label_width,
            )
            value = cell.text + cell.marker
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
            value_room = max(1, room - (2 + display_width(bar) if bar else 0))
            pieces = (
                wrap(value, value_room)
                if plan.wrap
                else [fit_text(column, value, value_room, theme)]
            )
            first = theme.paint(pieces[0], cell.style)
            if bar:
                first = f"{first}  {theme.paint(bar, cell.bar_style)}"
            lines.append(" " * indent + theme.header(label) + "  " + first)
            for extra in pieces[1:]:
                lines.append(" " * (indent + label_width + 2) + theme.paint(extra, cell.style))
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
            cells.append((cell.text + cell.marker).replace("|", "\\|"))
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


def render(table: Table, plan: Plan, theme: Theme, style: str = "box", summary: bool = True) -> str:
    """Render in the requested style, with the optional summary line."""
    if style == "md":
        return render_markdown(table, plan, theme)
    if style == "csv":
        return render_delimited(table, plan, ",")
    if style == "tsv":
        return render_delimited(table, plan, "\t")
    if style == "json":
        return render_json(table, plan)

    body = render_cards(table, plan, theme) if plan.cards else render_bordered(table, plan, theme)

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
                extra = extra.replace("·", "-")
            # The footer obeys the width budget too, wrapped rather than cut.
            for piece in wrap(extra, plan.width - 1):
                parts.append(" " + theme.header(piece))
    return "\n".join(parts)
