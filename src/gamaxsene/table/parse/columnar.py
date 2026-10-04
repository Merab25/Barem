"""Splitting classic command output into columns by position, not by split().

`line.split()` fails on real output in ways that matter:

- `df` has a header "Mounted on" that contains a space.
- `ps aux` has a COMMAND column holding a whole command line.
- `docker ps` has both: a "CONTAINER ID" header and a STATUS column reading
  "Exited (137) 5 hours ago".
- Numeric columns are right-aligned, so the header does not start where the
  data starts, and a wide value can start to the left of its own header.
- An empty value leaves a gap that split() silently collapses, shifting every
  later column on that row.

The parser works in two passes. The header says how many columns there are
and where each one begins; the data says where the values actually sit. Each
run of data is then assigned to the header column it ends inside, which
merges the pieces of a split phrase back together without ever needing to
guess at gap widths.
"""

from __future__ import annotations

import re

from ..width import sanitize

#: How many rows to sample when looking for separators. Enough to be sure,
#: cheap enough for a 50,000-row input.
SAMPLE = 200


def _clean_lines(text: str) -> list[str]:
    lines = [sanitize(line).rstrip() for line in text.splitlines()]
    return [line for line in lines if line.strip()]


def _blank_positions(lines: list[str], width: int) -> list[bool]:
    """For each position up to `width`, whether it is blank in every line.

    A position past the end of a line counts as blank, which is what makes a
    short value leave a detectable gap.
    """
    blank = [True] * width
    for line in lines:
        for i, char in enumerate(line[:width]):
            if char != " ":
                blank[i] = False
    return blank


def _runs(mask: list[bool]) -> list[tuple[int, int]]:
    """The (start, end) ranges where `mask` is True."""
    out: list[tuple[int, int]] = []
    start: int | None = None
    for i, flag in enumerate(mask):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def header_columns(header: str, data_lines: list[str], width: int) -> list[tuple[int, int]]:
    """The header's word runs, with multi-word headers merged into one.

    Counting words alone over-counts: "Mounted on" and "CONTAINER ID" are one
    column each. Two rules, each needed because the other misses a case.

    First, a word pair some row's value runs straight through is one column:

        CONTAINER ID    a1b2c3d4e5f6 runs through the gap   -> one column
        Mounted on      /boot/efi runs through the gap      -> one column
        Used Avail      every row is blank in the gap       -> two columns
        USER      PID   no row spans nine characters        -> two columns

    Second, a word only one space after its neighbour, with no data under it
    at all, is a continuation of that neighbour. This catches "Mounted on"
    when every mount point happens to be short. The single-space condition is
    what stops a genuinely empty column -- `docker ps` PORTS when nothing
    publishes a port -- from being swallowed by the header before it.
    """
    runs = [(m.start(), m.end()) for m in re.finditer(r"\S+", header)]
    if not runs:
        return []

    merged = [runs[0]]
    narrow_before = [False]
    for start, end in runs[1:]:
        prev_start, prev_end = merged[-1]
        gap = range(prev_end, start)
        bridged = bool(gap) and any(
            all(pos < len(line) and line[pos] != " " for pos in gap) for line in data_lines
        )
        if bridged:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
            narrow_before.append(len(gap) <= 1)

    regions = _regions([start for start, _ in merged], width)
    has_data = [any(line[lo:hi].strip() for line in data_lines) for lo, hi in regions]
    out: list[tuple[int, int]] = []
    for index, span in enumerate(merged):
        if index and narrow_before[index] and not has_data[index]:
            out[-1] = (out[-1][0], span[1])
        else:
            out.append(span)
    return out or merged


def _regions(starts: list[int], width: int) -> list[tuple[int, int]]:
    """Turn column start positions into [start, next_start) regions.

    The first column starts at 0 so a value wider than its header is not
    clipped, and the last runs past the end of every line.
    """
    if not starts:
        return []
    bounds = [0, *starts[1:], width + 1]
    return [(bounds[i], bounds[i + 1]) for i in range(len(starts))]


def _slice(line: str, start: int, end: int | None) -> str:
    return line[start:end].strip() if end is not None else line[start:].strip()


def parse(text: str, has_header: bool = True) -> tuple[list[str], list[list[str]]]:
    """Split columnar text into (headers, rows of cells).

    Returns empty lists when there is nothing usable, so the caller can fall
    back to printing the input unchanged.
    """
    lines = _clean_lines(text)
    if not lines:
        return [], []

    header_line = lines[0] if has_header else ""
    data_lines = lines[1:] if has_header else lines
    if has_header and not data_lines:
        return split_header(header_line), []
    if not data_lines:
        return [], []

    sample = data_lines[:SAMPLE]
    width = max(max(len(line) for line in sample), len(header_line))

    if has_header:
        columns = header_columns(header_line, sample, width)
        if len(columns) > 1:
            return _parse_with_header(header_line, data_lines, columns, width)

    # No usable header: fall back to the data's own gaps.
    spans = _spans_from_data(sample, width)
    if not spans:
        return ([header_line] if has_header else []), [[line] for line in data_lines]
    spans[-1] = (spans[-1][0], None)
    headers = (
        [_slice(header_line, s, e) or f"col{i + 1}" for i, (s, e) in enumerate(spans)]
        if has_header
        else []
    )
    rows = [[_slice(line, s, e) for s, e in spans] for line in data_lines]
    return _dedupe(headers), rows


def _spans_from_data(sample: list[str], width: int) -> list[tuple[int, int]]:
    """Field spans taken from positions that are blank in every data row."""
    blank = _blank_positions(sample, width)
    return [(s, e) for s, e in _runs([not b for b in blank])]


def _parse_with_header(
    header_line: str,
    data_lines: list[str],
    columns: list[tuple[int, int]],
    width: int,
) -> tuple[list[str], list[list[str]]]:
    """Assign each run of data to the header column it ends inside.

    This is what glues "Exited (137) 5 hours ago" back together: all four of
    its pieces end inside the STATUS region, so they merge, while "cache"
    ends inside NAMES and stays separate.
    """
    regions = _regions([start for start, _ in columns], width)
    headers = [
        _slice(header_line, start, end if end <= len(header_line) else None) or f"col{i + 1}"
        for i, (start, end) in enumerate(regions)
    ]

    def region_of(position: int) -> int:
        for index, (start, end) in enumerate(regions):
            if start <= position < end:
                return index
        return len(regions) - 1

    rows: list[list[str]] = []
    for line in data_lines:
        cells = [""] * len(regions)
        pieces: list[list[str]] = [[] for _ in regions]
        for start, end in _runs([char != " " for char in line]):
            # The end of a value decides which column it belongs to, which is
            # right for a right-aligned number wider than its own header.
            pieces[region_of(end - 1)].append(line[start:end])
        for index, parts in enumerate(pieces):
            cells[index] = " ".join(parts).strip()
        rows.append(cells)
    return _dedupe(headers), rows


def _dedupe(headers: list[str]) -> list[str]:
    """Make header names unique, since they become dictionary keys."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for header in headers:
        key = header
        if key in seen:
            seen[key] += 1
            key = f"{header}_{seen[header]}"
        else:
            seen[key] = 0
        out.append(key)
    return out


def split_header(header: str) -> list[str]:
    """Header words grouped on runs of two or more spaces.

    Not reliable on its own -- `df` separates "Used" and "Avail" by a single
    space -- but useful when there are no data rows to reason about.
    """
    return [chunk.strip() for chunk in header.split("  ") if chunk.strip()]


def parse_whitespace(
    text: str, has_header: bool = True, limit: int | None = None
) -> tuple[list[str], list[list[str]]]:
    """Simple whitespace split, with the last field taking the rest."""
    lines = _clean_lines(text)
    if not lines:
        return [], []
    headers = split_header(lines[0]) if has_header else []
    data_lines = lines[1:] if has_header else lines
    count = limit or (len(headers) if headers else 0)
    rows = [line.split(None, count - 1) if count else line.split() for line in data_lines]
    return headers, rows
