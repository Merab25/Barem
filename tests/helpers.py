"""Shared helpers for the table tests."""

from __future__ import annotations


def data_rows(out: str) -> list[str]:
    """The data lines of a clean-style table.

    Found by position -- after the rule, up to the blank line before the
    summary -- rather than by what a row starts with, because centred cells
    have leading padding and a row no longer begins with its own value.
    """
    lines = out.splitlines()
    start = 0
    for index, line in enumerate(lines):
        if line.strip() and set(line.strip()) <= {"─", "-"}:
            start = index + 1
            break
    rows: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            break
        rows.append(line)
    return rows
