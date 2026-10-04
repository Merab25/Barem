"""Parsers for input that already has structure: JSON, CSV, key=value."""

from __future__ import annotations

import csv
import io
import json

from ..width import sanitize


def _flatten(value, prefix: str = "") -> dict[str, str]:
    """Flatten nested objects into dotted keys, so a table can show them."""
    out: dict[str, str] = {}
    if isinstance(value, dict):
        for key, inner in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten(inner, name))
    elif isinstance(value, list):
        if value and all(not isinstance(v, (dict, list)) for v in value):
            out[prefix] = ", ".join("" if v is None else str(v) for v in value)
        else:
            for index, inner in enumerate(value):
                out.update(_flatten(inner, f"{prefix}[{index}]"))
    else:
        out[prefix] = "" if value is None else str(value)
    return out


def parse_json(text: str) -> tuple[list[str], list[list[str]]]:
    """A JSON array of objects, or a single object, as a table."""
    data = json.loads(text)
    if isinstance(data, dict):
        # A lone object: show it as key/value rows, which reads better than
        # one very wide row.
        flat = _flatten(data)
        return ["KEY", "VALUE"], [[k, sanitize(v)] for k, v in flat.items()]
    if not isinstance(data, list):
        raise ValueError("JSON root is neither an object nor an array")
    return _rows_from_dicts(
        [_flatten(item) if isinstance(item, dict) else {"value": str(item)} for item in data]
    )


def parse_jsonl(text: str) -> tuple[list[str], list[list[str]]]:
    """One JSON object per line, as structured logs produce."""
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        records.append(_flatten(obj) if isinstance(obj, dict) else {"value": str(obj)})
    return _rows_from_dicts(records)


def _rows_from_dicts(records: list[dict[str, str]]) -> tuple[list[str], list[list[str]]]:
    """Union of all keys in order of first appearance, so nothing is lost."""
    headers: list[str] = []
    for record in records:
        for key in record:
            if key not in headers:
                headers.append(key)
    rows = [[sanitize(str(record.get(h, ""))) for h in headers] for record in records]
    return headers, rows


def parse_delimited(text: str, delimiter: str | None = None) -> tuple[list[str], list[list[str]]]:
    """CSV or TSV, using the csv module so quoted separators survive."""
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = "\t" if "\t" in text.splitlines()[0] else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    records = [row for row in reader if any(cell.strip() for cell in row)]
    if not records:
        return [], []
    headers = [sanitize(h.strip()) or f"col{i + 1}" for i, h in enumerate(records[0])]
    width = len(headers)
    rows = []
    for record in records[1:]:
        cells = [sanitize(c.strip()) for c in record[:width]]
        cells += [""] * (width - len(cells))
        rows.append(cells)
    return headers, rows


def parse_keyvalue(text: str) -> tuple[list[str], list[list[str]]]:
    """`key=value` lines, as /etc/os-release and env produce."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        rows.append([sanitize(key.strip()), sanitize(value.strip().strip("\"'"))])
    return ["KEY", "VALUE"], rows
