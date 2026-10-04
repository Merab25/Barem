"""Profiles for systemd and session commands: systemctl, last."""

from __future__ import annotations

from ..model import Column, Kind, Profile
from ..theme import BAD, status_group


def unit_summary(rows: list[dict]) -> str:
    if not rows:
        return ""
    bad = sum(1 for r in rows if status_group(r.get("active", "")) == BAD)
    word = "unit" if len(rows) == 1 else "units"
    return f"{len(rows)} {word}" + (f" · {bad} not active" if bad else "")


SYSTEMCTL = Profile(
    name="systemctl list-units",
    fingerprint={"unit", "load", "active", "sub"},
    columns=[
        Column("unit", "UNIT", Kind.TEXT, priority=1, identity=True, min_width=14),
        Column("load", "LOAD", Kind.STATUS, priority=4),
        Column("active", "ACTIVE", Kind.STATUS, priority=1, min_width=8),
        Column("sub", "SUB", Kind.STATUS, priority=2),
        Column("description", "DESCRIPTION", Kind.TEXT, priority=3, min_width=10),
    ],
    summary=unit_summary,
)

SYSTEMCTL_FILES = Profile(
    name="systemctl list-unit-files",
    fingerprint={"unit file", "state"},
    columns=[
        Column("unit_file", "UNIT FILE", Kind.TEXT, priority=1, identity=True, min_width=14),
        Column("state", "STATE", Kind.STATUS, priority=1),
        Column("preset", "PRESET", Kind.STATUS, priority=3),
    ],
)

TIMERS = Profile(
    name="systemctl list-timers",
    fingerprint={"next", "left", "unit", "activates"},
    columns=[
        Column("next", "NEXT", Kind.TEXT, priority=2, min_width=10),
        Column("left", "LEFT", Kind.DURATION, priority=1),
        Column("last", "LAST", Kind.TEXT, priority=4, min_width=10),
        Column("passed", "PASSED", Kind.DURATION, priority=3),
        Column("unit", "UNIT", Kind.TEXT, priority=1, identity=True, min_width=12),
        Column("activates", "ACTIVATES", Kind.TEXT, priority=3, min_width=10),
    ],
)

PROFILES = [SYSTEMCTL, SYSTEMCTL_FILES, TIMERS]
