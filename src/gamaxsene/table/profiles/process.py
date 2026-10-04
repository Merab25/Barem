"""Profiles for process and memory commands: ps, free, top."""

from __future__ import annotations

from ..humanize import parse_percent
from ..model import Column, Kind, Profile


def ps_summary(rows: list[dict]) -> str:
    """12 processes · 34% cpu · 18% mem"""
    if not rows:
        return ""
    cpu = sum(parse_percent(r.get("cpu_pct", "")) or 0 for r in rows)
    mem = sum(parse_percent(r.get("mem_pct", "")) or 0 for r in rows)
    word = "process" if len(rows) == 1 else "processes"
    return f"{len(rows)} {word} · {cpu:.1f}% cpu · {mem:.1f}% mem"


PS_AUX = Profile(
    name="ps aux",
    fingerprint={"user", "pid", "%cpu", "%mem", "command"},
    columns=[
        Column("user", "USER", Kind.TEXT, priority=3, min_width=6),
        Column("pid", "PID", Kind.NUMBER, priority=1, identity=True),
        Column("cpu_pct", "%CPU", Kind.PERCENT, priority=1, warn=50, crit=90),
        Column("mem_pct", "%MEM", Kind.PERCENT, priority=1, warn=20, crit=50),
        # ps reports these in kilobytes, so humanizing them as bytes would
        # understate them by 1024x. Design rule 2: never lie.
        Column("vsz", "VSZ", Kind.NUMBER, priority=5, unit="KB"),
        Column("rss", "RSS", Kind.NUMBER, priority=3, unit="KB"),
        Column("tty", "TTY", Kind.TEXT, priority=5),
        Column("stat", "STAT", Kind.TEXT, priority=4),
        Column("start", "START", Kind.TIME, priority=5),
        Column("time", "TIME", Kind.DURATION, priority=4),
        Column("command", "COMMAND", Kind.TEXT, priority=2, min_width=12),
    ],
    summary=ps_summary,
)

PS_EF = Profile(
    name="ps -ef",
    fingerprint={"uid", "pid", "ppid", "cmd"},
    columns=[
        Column("uid", "UID", Kind.TEXT, priority=3, min_width=6),
        Column("pid", "PID", Kind.NUMBER, priority=1, identity=True),
        Column("ppid", "PPID", Kind.NUMBER, priority=3),
        Column("c", "C", Kind.NUMBER, priority=5),
        Column("stime", "STIME", Kind.TIME, priority=5),
        Column("tty", "TTY", Kind.TEXT, priority=5),
        Column("time", "TIME", Kind.DURATION, priority=4),
        Column("cmd", "CMD", Kind.TEXT, priority=2, min_width=12),
    ],
)

FREE = Profile(
    name="free",
    fingerprint={"total", "used", "free", "available"},
    columns=[
        Column("kind", "", Kind.TEXT, priority=1, identity=True, min_width=6),
        Column("total", "TOTAL", Kind.SIZE, priority=1),
        Column("used", "USED", Kind.SIZE, priority=1),
        Column("free", "FREE", Kind.SIZE, priority=2),
        Column("shared", "SHARED", Kind.SIZE, priority=5),
        Column("buff_cache", "BUFF/CACHE", Kind.SIZE, priority=4),
        Column("available", "AVAILABLE", Kind.SIZE, priority=2),
    ],
)

PROFILES = [PS_AUX, PS_EF, FREE]
