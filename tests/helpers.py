"""Shared helpers for the table tests."""

from __future__ import annotations

#: Characters that only ever appear in a border or a rule.
_BORDER = set("┌┐└┘├┤┬┴┼─+-")
#: Vertical separators, removed so a cell can be read without them.
_PIPES = ("│", "|")


def _is_border(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and set(stripped) <= _BORDER


def _without_pipes(line: str) -> str:
    for pipe in _PIPES:
        line = line.replace(pipe, " ")
    return line


def _body(out: str) -> list[str]:
    """The header and data lines, with borders and pipes taken out.

    Written to work for both styles: the box style wraps every row in pipes
    and brackets the table in rules, the clean style has one rule under the
    header. Dropping border-only lines leaves the same shape either way.
    """
    lines = [_without_pipes(line) for line in out.splitlines() if not _is_border(line)]
    body: list[str] = []
    for line in lines:
        if not line.strip() and body:
            break  # the blank line before the summary
        if line.strip():
            body.append(line)
    return body


def header_line(out: str) -> str:
    """The header row, whatever style the table was drawn in."""
    body = _body(out)
    return body[0] if body else ""


def data_rows(out: str) -> list[str]:
    """The data rows, whatever style the table was drawn in.

    Found by position rather than by what a row starts with, since centred
    cells have leading padding and the box style starts every row with a pipe.
    """
    return _body(out)[1:]
