"""Profiles for network commands: ss, ip -br, netstat."""

from __future__ import annotations

from ..model import Column, Kind, Profile

SS = Profile(
    name="ss",
    fingerprint={"state", "recv-q", "send-q", "local address:port"},
    columns=[
        Column("state", "STATE", Kind.STATUS, priority=2, min_width=8),
        Column("recv_q", "RECV-Q", Kind.NUMBER, priority=4),
        Column("send_q", "SEND-Q", Kind.NUMBER, priority=4),
        Column("local", "LOCAL ADDRESS:PORT", Kind.TEXT, priority=1, identity=True, min_width=16),
        Column("peer", "PEER ADDRESS:PORT", Kind.TEXT, priority=2, min_width=11),
        Column("process", "PROCESS", Kind.TEXT, priority=3, min_width=10),
    ],
    summary=lambda rows: f"{len(rows)} sockets",
)

IP_BRIEF = Profile(
    name="ip -br a",
    fingerprint={"interface", "state", "addresses"},
    columns=[
        Column("interface", "INTERFACE", Kind.TEXT, priority=1, identity=True, min_width=8),
        Column("state", "STATE", Kind.STATUS, priority=1, min_width=8),
        Column("addresses", "ADDRESSES", Kind.TEXT, priority=2, min_width=12),
    ],
    summary=lambda rows: f"{len(rows)} interfaces",
)

NETSTAT = Profile(
    name="netstat",
    fingerprint={"proto", "recv-q", "send-q", "local address", "foreign address"},
    columns=[
        Column("proto", "PROTO", Kind.TEXT, priority=3),
        Column("recv_q", "RECV-Q", Kind.NUMBER, priority=4),
        Column("send_q", "SEND-Q", Kind.NUMBER, priority=4),
        Column("local", "LOCAL ADDRESS", Kind.TEXT, priority=1, identity=True, min_width=12),
        Column("foreign", "FOREIGN ADDRESS", Kind.TEXT, priority=2, min_width=10),
        Column("state", "STATE", Kind.STATUS, priority=1, min_width=8),
        Column("program", "PID/PROGRAM NAME", Kind.TEXT, priority=3, min_width=10),
    ],
    summary=lambda rows: f"{len(rows)} connections",
)

PROFILES = [SS, IP_BRIEF, NETSTAT]
