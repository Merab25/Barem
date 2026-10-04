"""Turning raw values into readable ones, and back again for sorting.

Every `human_*` function has a `parse_*` partner, because sorting has to work
on the real value: "1.8T" must sort above "512M", not below it alphabetically.
"""

from __future__ import annotations

import re

_SIZE_UNITS = ["B", "K", "M", "G", "T", "P", "E"]

#: 1.8T, 512M, 2.1Mi, 43 GB, 100k — the forms real commands print.
SIZE_RE = re.compile(
    r"^\s*([+-]?\d+(?:[.,]\d+)?)\s*([KMGTPEkmgtpe])?(?:i?[Bb]?)?\s*$",
)
PERCENT_RE = re.compile(r"^\s*([+-]?\d+(?:[.,]\d+)?)\s*%\s*$")
NUMBER_RE = re.compile(r"^\s*([+-]?\d{1,3}(?:[ ,]\d{3})*(?:[.,]\d+)?|[+-]?\d+(?:[.,]\d+)?)\s*$")
#: 2d4h, 18m, 5.2s, 1-02:03:04, 02:03:04, 03:04
DURATION_RE = re.compile(
    r"^\s*(?:(\d+)-)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?\s*$", re.IGNORECASE
)
CLOCK_RE = re.compile(r"^\s*(?:(\d+)-)?(\d{1,3}):(\d{2})(?::(\d{2}))?\s*$")
TIME_RE = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?\s*$")


def human_size(value: float, precision: int | None = None) -> str:
    """1.8T, 512M, 43G — the compact form `df -h` and `ls -h` use."""
    if value < 0:
        return "-" + human_size(-value, precision)
    size = float(value)
    index = 0
    while size >= 1024 and index < len(_SIZE_UNITS) - 1:
        size /= 1024
        index += 1
    unit = _SIZE_UNITS[index]
    if precision is not None:
        return f"{size:.{precision}f}{unit}"
    if index == 0:
        return f"{int(size)}{unit}"
    # One decimal below 10, none above, which is what the eye expects.
    return f"{size:.1f}{unit}" if size < 10 else f"{size:.0f}{unit}"


def parse_size(text: str) -> float | None:
    """Bytes from any of the size forms commands print, for sorting."""
    if text is None:
        return None
    stripped = text.strip()
    if stripped in ("", "-", "0"):
        return 0.0 if stripped == "0" else None
    match = SIZE_RE.match(stripped)
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    suffix = (match.group(2) or "B").upper()
    return number * (1024 ** _SIZE_UNITS.index(suffix))


def parse_percent(text: str) -> float | None:
    """The number out of "95%", or out of a bare number in a percent column."""
    if text is None:
        return None
    match = PERCENT_RE.match(text)
    if match:
        return float(match.group(1).replace(",", "."))
    bare = text.strip()
    try:
        return float(bare.replace(",", "."))
    except ValueError:
        return None


def parse_number(text: str) -> float | None:
    """A number, tolerating thousands separators."""
    if text is None or not NUMBER_RE.match(text):
        return None
    cleaned = text.strip().replace(" ", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def human_number(value: float) -> str:
    """Thousands separators, and no trailing .0 on whole numbers."""
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


def parse_duration(text: str) -> float | None:
    """Seconds from "2d 4h", "18m", "5.2s", "1-02:03:04" or "02:03"."""
    if text is None:
        return None
    stripped = text.strip()
    if not stripped or stripped == "-":
        return None

    clock = CLOCK_RE.match(stripped)
    if clock:
        days = int(clock.group(1) or 0)
        a, b, c = clock.group(2), clock.group(3), clock.group(4)
        if c is None:  # MM:SS
            return days * 86400 + int(a) * 60 + int(b)
        return days * 86400 + int(a) * 3600 + int(b) * 60 + int(c)

    compact = stripped.replace(" ", "")
    match = DURATION_RE.match(compact)
    if not match or not any(match.groups()):
        return None
    weeks, days, hours, minutes, seconds = match.groups()
    return (
        int(weeks or 0) * 86400
        + int(days or 0) * 86400
        + int(hours or 0) * 3600
        + int(minutes or 0) * 60
        + float(seconds or 0)
    )


def human_duration(seconds: float) -> str:
    """2d 4h, 18m, 5.2s — two units at most, so it stays short."""
    if seconds < 0:
        return "-" + human_duration(-seconds)
    if seconds < 1:
        return f"{seconds:.2f}s".replace("0.", ".")
    if seconds < 60:
        return f"{seconds:.1f}s" if seconds < 10 else f"{int(seconds)}s"
    minutes, sec = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m" if sec == 0 else f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h" if minutes == 0 else f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d" if hours == 0 else f"{days}d {hours}h"


def human_relative(seconds: float) -> str:
    """ "3 min ago", "2 days ago" — for --relative."""
    if seconds < 0:
        return "in " + human_relative(-seconds).removesuffix(" ago")
    if seconds < 45:
        return "just now"
    if seconds < 5400:
        return f"{round(seconds / 60)} min ago"
    if seconds < 86400:
        return f"{round(seconds / 3600)} hr ago"
    days = round(seconds / 86400)
    return "yesterday" if days == 1 else f"{days} days ago"


def sort_value(text: str, kind: str) -> tuple[int, float, str]:
    """A sort key that orders by real value, with empties last.

    Returns a tuple so mixed or unparsable cells never raise: the first element
    buckets parsed values before unparsable ones before empty ones.
    """
    raw = (text or "").strip()
    if not raw or raw == "-":
        return (2, 0.0, "")

    parsers = {
        "size": parse_size,
        "percent": parse_percent,
        "number": parse_number,
        "duration": parse_duration,
    }
    parser = parsers.get(str(kind))
    if parser is not None:
        value = parser(raw)
        if value is not None:
            return (0, value, "")
    # A text column still sorts numerically when every value happens to be one.
    value = parse_number(raw)
    if value is not None:
        return (0, value, "")
    return (1, 0.0, raw.lower())
