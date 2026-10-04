"""Guessing what each column means when no profile matches.

This is the path that runs for every command nobody wrote a profile for, so
it has to be good. A kind is only assigned when most of the non-empty values
in the column agree, which keeps one odd row from mislabelling the column.
"""

from __future__ import annotations

import re

from ..humanize import (
    DURATION_RE,
    NUMBER_RE,
    PERCENT_RE,
    SIZE_RE,
    TIME_RE,
)
from ..model import Column, Kind
from ..theme import NEUTRAL, status_group

#: Fraction of non-empty values that must agree before a kind is assigned.
AGREEMENT = 0.8

#: Headers that name a percentage even when the values are bare numbers.
PERCENT_HEADERS = {"%cpu", "%mem", "use%", "cpu%", "mem%", "iuse%", "capacity", "pct", "%"}
SIZE_HEADERS = {
    "size",
    "used",
    "avail",
    "available",
    "free",
    "total",
    "rss",
    "vsz",
    "shared",
    "buff/cache",
    "disk",
    "mem",
    "memory",
    "cache",
    "quota",
    "limit",
    "fssize",
    "fsused",
    "fsavail",
}
TIME_HEADERS = {"time", "start", "started", "stime", "created", "when", "last", "date"}
DURATION_HEADERS = {"elapsed", "etime", "uptime", "age", "duration", "runtime", "cputime"}
STATUS_HEADERS = {"status", "state", "st", "stat", "health", "ready", "active", "sub", "load"}
PATH_HEADERS = {
    "filesystem",
    "mounted on",
    "mountpoint",
    "mountpoints",
    "target",
    "path",
    "source",
    "device",
    "file",
    "dir",
    "directory",
    "name",
    "command",
}
IDENTITY_HEADERS = {
    "filesystem",
    "name",
    "names",
    "container id",
    "pod",
    "unit",
    "device",
    "interface",
    "iface",
    "image",
    "user",
    "pid",
    "id",
    "netid",
    "key",
}


def _is(pattern: re.Pattern, value: str) -> bool:
    return bool(pattern.match(value))


def _looks_like_size(value: str) -> bool:
    match = SIZE_RE.match(value)
    # A bare integer is a number, not a size: a size carries a unit letter.
    return bool(match and match.group(2))


def _looks_like_path(value: str) -> bool:
    return value.startswith("/") or value.startswith("~/") or value.startswith("./")


def _ratio(values: list[str], test) -> float:
    if not values:
        return 0.0
    return sum(1 for v in values if test(v)) / len(values)


def infer_kind(header: str, values: list[str]) -> Kind:
    """The kind of one column, from its header and its values."""
    name = header.strip().lower()
    present = [v for v in values if v and v.strip() and v.strip() != "-"]

    # The header is the strongest signal when it names a unit.
    if name in PERCENT_HEADERS or name.endswith("%") or name.startswith("%"):
        return Kind.PERCENT
    if present and _ratio(present, lambda v: _is(PERCENT_RE, v)) >= AGREEMENT:
        return Kind.PERCENT

    if present and _ratio(present, _looks_like_size) >= AGREEMENT:
        return Kind.SIZE
    if (
        name in SIZE_HEADERS
        and present
        and _ratio(present, lambda v: _is(NUMBER_RE, v)) >= AGREEMENT
    ):
        return Kind.SIZE

    if name in DURATION_HEADERS:
        return Kind.DURATION

    def looks_duration(value: str) -> bool:
        return _is(DURATION_RE, value) and not _is(NUMBER_RE, value)

    if present and _ratio(present, looks_duration) >= AGREEMENT:
        return Kind.DURATION

    if name in TIME_HEADERS and present and _ratio(present, lambda v: _is(TIME_RE, v)) >= AGREEMENT:
        return Kind.TIME
    if present and _ratio(present, lambda v: _is(TIME_RE, v)) >= AGREEMENT:
        return Kind.TIME

    if present and _ratio(present, lambda v: _is(NUMBER_RE, v)) >= AGREEMENT:
        return Kind.NUMBER

    if name in STATUS_HEADERS:
        return Kind.STATUS
    if present and _ratio(present, lambda v: status_group(v) != NEUTRAL) >= AGREEMENT:
        return Kind.STATUS

    if name in PATH_HEADERS and name != "name" and name != "command":
        return Kind.PATH
    if present and _ratio(present, _looks_like_path) >= AGREEMENT:
        return Kind.PATH

    return Kind.TEXT


def _min_width(header: str, kind: Kind, identity: bool) -> int:
    """How narrow a column may get before the layout should drop one instead.

    Truncating to three characters makes a column worthless while still
    costing space, so every flexible column keeps a floor wide enough to be
    recognisable, and the identity column keeps a larger one.
    """
    label = len(header.strip())
    if kind is Kind.STATUS:
        return 8
    if identity:
        return max(10, min(14, label))
    if kind is Kind.PATH:
        return max(8, min(14, label))
    if kind is Kind.TEXT:
        return max(6, min(12, label))
    return max(3, min(10, label))


def _priority(index: int, total: int, kind: Kind, identity: bool) -> int:
    """Which columns to give up first when the terminal is narrow.

    1 never drops. Percentages are the alert in most commands, so they rank
    with the identity column. Trailing text columns go first.
    """
    if identity:
        return 1
    if kind is Kind.PERCENT:
        return 1
    if kind in (Kind.SIZE, Kind.NUMBER):
        return 2
    if kind is Kind.STATUS:
        return 2
    if index >= total - 1:
        return 3  # the last column is often the mount point or command
    return 4


def infer_columns(headers: list[str], rows: list[list[str]]) -> list[Column]:
    """Build a full column spec from headers and data alone."""
    columns: list[Column] = []
    total = len(headers)
    identity_taken = False

    for index, header in enumerate(headers):
        values = [row[index] if index < len(row) else "" for row in rows]
        kind = infer_kind(header, values)
        name = header.strip().lower()

        identity = False
        if not identity_taken and (index == 0 or name in IDENTITY_HEADERS):
            # The identifying column names the row; it is never dropped and
            # becomes the heading in card mode.
            identity = kind in (Kind.TEXT, Kind.PATH, Kind.STATUS, Kind.NUMBER)
            identity_taken = identity

        key = re.sub(r"[^a-z0-9]+", "_", name).strip("_") or f"col{index + 1}"
        columns.append(
            Column(
                key=key,
                header=header.strip().upper() or f"COL{index + 1}",
                kind=kind,
                priority=_priority(index, total, kind, identity),
                identity=identity,
                # A floor that keeps the column readable. Shrinking stops
                # here, which is what pushes the layout on to dropping a
                # low-priority column instead of squeezing every one of them
                # down to "CO...".
                min_width=_min_width(header, kind, identity),
            )
        )

    if columns and not identity_taken:
        columns[0].identity = True
        columns[0].priority = 1
    return columns
