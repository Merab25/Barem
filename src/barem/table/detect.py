"""Working out what the input is, and which command produced it."""

from __future__ import annotations

import json
import re

from .model import Table
from .parse import columnar, infer, structured
from .profiles import by_name, match

JSON = "json"
JSONL = "jsonl"
CSV = "csv"
TSV = "tsv"
KEYVALUE = "keyvalue"
COLUMNAR = "columnar"

INPUT_FORMATS = (JSON, JSONL, CSV, TSV, KEYVALUE, COLUMNAR)

_KEYVALUE_RE = re.compile(r"^\s*[\w.\-]+=")


def detect_format(text: str) -> str:
    """Which input format this is, from the text alone."""
    stripped = text.strip()
    if not stripped:
        return COLUMNAR

    if stripped[0] in "[{":
        try:
            json.loads(stripped)
            return JSON
        except ValueError:
            pass  # could still be JSON lines

    lines = [line for line in stripped.splitlines() if line.strip()]
    if lines and all(line.strip()[0] == "{" for line in lines):
        try:
            for line in lines[:20]:
                json.loads(line)
            return JSONL
        except ValueError:
            pass

    if len(lines) >= 2:
        # A consistent separator count across lines means a delimited file.
        for sep, name in (("\t", TSV), (",", CSV)):
            counts = {line.count(sep) for line in lines[:20]}
            if len(counts) == 1 and counts.pop() >= 1:
                return name

    if lines and sum(1 for line in lines if _KEYVALUE_RE.match(line)) >= max(
        2, int(len(lines) * 0.8)
    ):
        return KEYVALUE

    return COLUMNAR


def parse_input(
    text: str,
    input_format: str | None = None,
    has_header: bool = True,
) -> tuple[list[str], list[list[str]], str]:
    """Headers, rows and the format that was used.

    Falls back to columnar parsing if a structured parse fails, because a
    formatting tool must never be the reason output cannot be read.
    """
    fmt = input_format or detect_format(text)
    try:
        if fmt == JSON:
            headers, rows = structured.parse_json(text)
        elif fmt == JSONL:
            headers, rows = structured.parse_jsonl(text)
        elif fmt in (CSV, TSV):
            headers, rows = structured.parse_delimited(text, "\t" if fmt == TSV else None)
        elif fmt == KEYVALUE:
            headers, rows = structured.parse_keyvalue(text)
        else:
            headers, rows = columnar.parse(text, has_header=has_header)
    except Exception:
        headers, rows = columnar.parse(text, has_header=has_header)
        fmt = COLUMNAR
    return headers, rows, fmt


def build_table(
    text: str,
    profile_name: str | None = None,
    input_format: str | None = None,
    has_header: bool = True,
    use_profiles: bool = True,
) -> Table | None:
    """Parse input into a Table, applying a profile when one matches.

    Returns None when there is nothing to render, which tells the caller to
    print the input unchanged.
    """
    headers, rows, _fmt = parse_input(text, input_format, has_header)
    if not headers and not rows:
        return None

    profile = None
    if profile_name:
        profile = by_name(profile_name)
    elif use_profiles and headers:
        profile = match(headers)

    if profile is not None:
        columns = _align_profile(profile, headers, rows)
        name = profile.name
    else:
        columns = infer.infer_columns(headers, rows)
        name = None

    if not columns:
        return None

    keyed = []
    for row in rows:
        record = {}
        for index, column in enumerate(columns):
            record[column.key] = row[index] if index < len(row) else ""
        keyed.append(record)

    summary_fn = profile.summary if profile is not None else None
    table = Table(columns=columns, rows=keyed, name=name, summary_fn=summary_fn)
    table.recompute_summary()
    return table


def _align_profile(profile, headers: list[str], rows: list[list[str]]):
    """Fit a profile's columns to however many fields were actually parsed.

    Real output varies: `ps aux` on one system has an extra column, `lsblk`
    drops MOUNTPOINTS when nothing is mounted. The profile describes the
    normal case, so trailing columns are trimmed and surplus fields get
    inferred columns rather than being thrown away.
    """
    found = max((len(row) for row in rows), default=len(headers))
    found = max(found, 1)
    columns = [
        type(c)(
            key=c.key,
            header=c.header,
            kind=c.kind,
            align=c.align,
            priority=c.priority,
            min_width=c.min_width,
            max_width=c.max_width,
            truncate=c.truncate,
            unit=c.unit,
            identity=c.identity,
            warn=c.warn,
            crit=c.crit,
            invert=c.invert,
        )
        for c in profile.columns[:found]
    ]
    if found > len(profile.columns):
        extra_headers = headers[len(profile.columns) : found]
        extra_rows = [row[len(profile.columns) : found] for row in rows]
        if not extra_headers:
            extra_headers = [f"col{i + 1}" for i in range(found - len(profile.columns))]
        columns.extend(infer.infer_columns(extra_headers, extra_rows))
    return columns
