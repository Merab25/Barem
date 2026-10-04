"""Profiles for container and cluster commands: docker, podman, kubectl."""

from __future__ import annotations

from ..model import Column, Kind, Profile
from ..theme import BAD, status_group


def container_summary(rows: list[dict]) -> str:
    """4 containers · 3 up · 1 exited"""
    if not rows:
        return ""
    up = sum(1 for r in rows if status_group(r.get("status", "")) == "good")
    bad = sum(1 for r in rows if status_group(r.get("status", "")) == BAD)
    word = "container" if len(rows) == 1 else "containers"
    parts = [f"{len(rows)} {word}"]
    if up:
        parts.append(f"{up} up")
    if bad:
        parts.append(f"{bad} not running")
    return " · ".join(parts)


def pod_summary(rows: list[dict]) -> str:
    if not rows:
        return ""
    bad = sum(1 for r in rows if status_group(r.get("status", "")) == BAD)
    word = "pod" if len(rows) == 1 else "pods"
    return f"{len(rows)} {word}" + (f" · {bad} unhealthy" if bad else "")


DOCKER_PS = Profile(
    name="docker ps",
    fingerprint={"container id", "image", "status"},
    columns=[
        Column("container_id", "CONTAINER ID", Kind.TEXT, priority=4, min_width=12, max_width=12),
        Column("image", "IMAGE", Kind.TEXT, priority=2, min_width=10),
        Column("command", "COMMAND", Kind.TEXT, priority=5, min_width=8),
        Column("created", "CREATED", Kind.TEXT, priority=4, min_width=7),
        Column("status", "STATUS", Kind.STATUS, priority=1, min_width=10),
        Column("ports", "PORTS", Kind.TEXT, priority=3, min_width=8),
        Column("names", "NAMES", Kind.TEXT, priority=1, identity=True, min_width=10),
    ],
    summary=container_summary,
)

DOCKER_IMAGES = Profile(
    name="docker images",
    fingerprint={"repository", "tag", "image id", "size"},
    columns=[
        Column("repository", "REPOSITORY", Kind.TEXT, priority=1, identity=True, min_width=10),
        Column("tag", "TAG", Kind.TEXT, priority=1),
        Column("image_id", "IMAGE ID", Kind.TEXT, priority=4, min_width=12, max_width=12),
        Column("created", "CREATED", Kind.TEXT, priority=3, min_width=7),
        Column("size", "SIZE", Kind.SIZE, priority=1),
    ],
    summary=lambda rows: f"{len(rows)} images",
)

KUBECTL_PODS = Profile(
    name="kubectl get pods",
    fingerprint={"name", "ready", "status", "restarts", "age"},
    columns=[
        Column("name", "NAME", Kind.TEXT, priority=1, identity=True, min_width=12),
        Column("ready", "READY", Kind.TEXT, priority=1),
        Column("status", "STATUS", Kind.STATUS, priority=1, min_width=10),
        Column("restarts", "RESTARTS", Kind.NUMBER, priority=2),
        Column("age", "AGE", Kind.DURATION, priority=3),
        Column("ip", "IP", Kind.TEXT, priority=4),
        Column("node", "NODE", Kind.TEXT, priority=4, min_width=8),
    ],
    summary=pod_summary,
)

KUBECTL_NODES = Profile(
    name="kubectl get nodes",
    fingerprint={"name", "status", "roles", "age", "version"},
    columns=[
        Column("name", "NAME", Kind.TEXT, priority=1, identity=True, min_width=10),
        Column("status", "STATUS", Kind.STATUS, priority=1),
        Column("roles", "ROLES", Kind.TEXT, priority=3),
        Column("age", "AGE", Kind.DURATION, priority=3),
        Column("version", "VERSION", Kind.TEXT, priority=2),
    ],
    summary=lambda rows: f"{len(rows)} nodes",
)

PROFILES = [DOCKER_PS, DOCKER_IMAGES, KUBECTL_PODS, KUBECTL_NODES]
