"""Profiles for disk and filesystem commands: df, lsblk, du, mount."""

from __future__ import annotations

from ..humanize import human_size, parse_percent, parse_size
from ..model import Column, Kind, Profile


def _sum_sizes(rows: list[dict], key: str) -> float:
    total = 0.0
    for row in rows:
        value = parse_size(row.get(key, ""))
        if value:
            total += value
    return total


def df_summary(rows: list[dict]) -> str:
    """4 filesystems · 2.3T total · 1.8T used (78%)"""
    if not rows:
        return ""
    total = _sum_sizes(rows, "size")
    used = _sum_sizes(rows, "used")
    word = "filesystem" if len(rows) == 1 else "filesystems"
    parts = [f"{len(rows)} {word}"]
    if total:
        parts.append(f"{human_size(total)} total")
        parts.append(f"{human_size(used)} used ({used / total * 100:.0f}%)")
    return " · ".join(parts)


def df_inode_summary(rows: list[dict]) -> str:
    if not rows:
        return ""
    word = "filesystem" if len(rows) == 1 else "filesystems"
    high = [r for r in rows if (parse_percent(r.get("iuse_pct", "")) or 0) >= 90]
    note = f" · {len(high)} above 90%" if high else ""
    return f"{len(rows)} {word}{note}"


DF = Profile(
    name="df",
    fingerprint={"filesystem", "size", "used", "avail"},
    columns=[
        Column("filesystem", "FILESYSTEM", Kind.PATH, priority=1, identity=True, min_width=12),
        Column("size", "SIZE", Kind.SIZE, priority=2),
        Column("used", "USED", Kind.SIZE, priority=3),
        Column("avail", "AVAIL", Kind.SIZE, priority=2),
        Column("use_pct", "USE%", Kind.PERCENT, priority=1, warn=70, crit=90),
        Column("target", "MOUNTED ON", Kind.PATH, priority=1, min_width=8),
    ],
    summary=df_summary,
)

DF_INODES = Profile(
    name="df -i",
    fingerprint={"filesystem", "inodes", "iused", "ifree"},
    columns=[
        Column("filesystem", "FILESYSTEM", Kind.PATH, priority=1, identity=True, min_width=12),
        Column("inodes", "INODES", Kind.NUMBER, priority=3),
        Column("iused", "IUSED", Kind.NUMBER, priority=3),
        Column("ifree", "IFREE", Kind.NUMBER, priority=2),
        Column("iuse_pct", "IUSE%", Kind.PERCENT, priority=1, warn=70, crit=90),
        Column("target", "MOUNTED ON", Kind.PATH, priority=1, min_width=8),
    ],
    summary=df_inode_summary,
)

LSBLK = Profile(
    name="lsblk",
    fingerprint={"name", "maj:min", "rm", "size", "ro", "type"},
    columns=[
        Column("name", "NAME", Kind.TEXT, priority=1, identity=True, min_width=8),
        Column("maj_min", "MAJ:MIN", Kind.TEXT, priority=5),
        Column("rm", "RM", Kind.TEXT, priority=5),
        Column("size", "SIZE", Kind.SIZE, priority=1),
        Column("ro", "RO", Kind.TEXT, priority=5),
        Column("type", "TYPE", Kind.TEXT, priority=3),
        Column("mountpoints", "MOUNTPOINTS", Kind.PATH, priority=2, min_width=8),
    ],
    summary=lambda rows: f"{len(rows)} devices",
)

LSBLK_FS = Profile(
    name="lsblk -f",
    fingerprint={"name", "fstype", "fsavail", "fsuse%"},
    columns=[
        Column("name", "NAME", Kind.TEXT, priority=1, identity=True, min_width=8),
        Column("fstype", "FSTYPE", Kind.TEXT, priority=3),
        Column("label", "LABEL", Kind.TEXT, priority=4),
        Column("uuid", "UUID", Kind.TEXT, priority=5, max_width=36),
        Column("fsavail", "FSAVAIL", Kind.SIZE, priority=2),
        Column("fsuse_pct", "FSUSE%", Kind.PERCENT, priority=1, warn=70, crit=90),
        Column("mountpoints", "MOUNTPOINTS", Kind.PATH, priority=1, min_width=8),
    ],
)

MOUNT = Profile(
    name="findmnt",
    fingerprint={"target", "source", "fstype", "options"},
    columns=[
        Column("target", "TARGET", Kind.PATH, priority=1, identity=True, min_width=10),
        Column("source", "SOURCE", Kind.PATH, priority=2, min_width=8),
        Column("fstype", "FSTYPE", Kind.TEXT, priority=2),
        Column("options", "OPTIONS", Kind.TEXT, priority=4, min_width=8),
    ],
    summary=lambda rows: f"{len(rows)} mounts",
)

PROFILES = [DF, DF_INODES, LSBLK, LSBLK_FS, MOUNT]
