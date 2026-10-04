"""The column model every parser fills in and every renderer reads."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum


class Kind(str, Enum):
    """What a column means, which decides how it is rendered and sorted."""

    TEXT = "text"
    NUMBER = "number"
    SIZE = "size"
    PERCENT = "percent"
    STATUS = "status"
    PATH = "path"
    TIME = "time"
    DURATION = "duration"


class Align(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"


class Trunc(str, Enum):
    END = "end"
    MIDDLE = "middle"
    NONE = "none"


#: Numbers are never truncated: the layout takes the space from a text column
#: instead, and only drops a numeric column as a last resort.
NUMERIC_KINDS = frozenset({Kind.NUMBER, Kind.SIZE, Kind.PERCENT, Kind.DURATION})

#: Columns the layout is allowed to shrink.
FLEXIBLE_KINDS = frozenset({Kind.TEXT, Kind.PATH, Kind.STATUS})

_DEFAULT_ALIGN = {
    Kind.TEXT: Align.LEFT,
    Kind.PATH: Align.LEFT,
    Kind.STATUS: Align.LEFT,
    Kind.NUMBER: Align.RIGHT,
    Kind.SIZE: Align.RIGHT,
    Kind.PERCENT: Align.RIGHT,
    Kind.TIME: Align.RIGHT,
    Kind.DURATION: Align.RIGHT,
}

_DEFAULT_TRUNC = {
    Kind.PATH: Trunc.MIDDLE,
    Kind.TEXT: Trunc.END,
    Kind.STATUS: Trunc.END,
}


@dataclass
class Column:
    """One column of a table.

    `priority` drives the responsive layout: 1 is never dropped, 5 is dropped
    first. `identity` marks the column that names the row, which is never
    dropped and becomes the heading in card mode.
    """

    key: str
    header: str
    kind: Kind = Kind.TEXT
    align: Align | None = None
    priority: int = 3
    min_width: int = 3
    max_width: int | None = None
    truncate: Trunc | None = None
    unit: str | None = None
    identity: bool = False
    warn: float | None = None
    crit: float | None = None
    invert: bool = False

    def __post_init__(self) -> None:
        if self.align is None:
            self.align = _DEFAULT_ALIGN.get(self.kind, Align.LEFT)
        if self.truncate is None:
            self.truncate = _DEFAULT_TRUNC.get(self.kind, Trunc.NONE)
        if self.identity and self.priority != 1:
            self.priority = 1

    @property
    def numeric(self) -> bool:
        return self.kind in NUMERIC_KINDS

    @property
    def flexible(self) -> bool:
        return self.kind in FLEXIBLE_KINDS


#: A parsed row: column key -> raw string value.
Row = dict


@dataclass
class Table:
    """Columns, rows, and where they came from."""

    columns: list[Column]
    rows: list[Row]
    name: str | None = None
    summary: str | None = None
    notes: list[str] = field(default_factory=list)
    #: Kept so the summary can be recomputed after rows are filtered away,
    #: otherwise `--where` leaves a line describing rows that are not shown.
    summary_fn: Callable[[list[Row]], str] | None = None

    def recompute_summary(self) -> None:
        if self.summary_fn is not None:
            try:
                self.summary = self.summary_fn(self.rows)
                return
            except Exception:
                pass
        noun = "row" if len(self.rows) == 1 else "rows"
        self.summary = f"{len(self.rows)} {noun}"

    def column(self, key: str) -> Column | None:
        key = key.lower()
        for col in self.columns:
            if col.key.lower() == key or col.header.lower() == key:
                return col
        return None

    def identity_column(self) -> Column | None:
        for col in self.columns:
            if col.identity:
                return col
        return self.columns[0] if self.columns else None


@dataclass
class Profile:
    """A known command: how to recognise it and what its columns mean."""

    name: str
    fingerprint: set[str]
    columns: list[Column]
    summary: Callable[[list[Row]], str] | None = None
    #: Header words that must not be present, to separate similar commands.
    excludes: set[str] = field(default_factory=set)

    def matches(self, headers: Iterable[str]) -> bool:
        words = {h.strip().lower() for h in headers}
        if self.excludes & words:
            return False
        return self.fingerprint <= words

    @property
    def score(self) -> int:
        """Longer fingerprints win, so `docker ps` beats a generic match."""
        return len(self.fingerprint)
