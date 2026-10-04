"""Known commands: how to recognise them and what their columns mean.

A profile is matched by its header fingerprint, because the pipe hands us
bytes and not a command name. Fingerprints are sets of header words, and the
longest matching fingerprint wins, so `docker ps` beats a looser match.

Users can drop extra profiles into ~/.config/gamaxsene/profiles/ as small
Python modules exposing a module-level `PROFILE`.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..model import Profile
from . import containers, disk, network, process, system

BUILTIN: list[Profile] = [
    *disk.PROFILES,
    *process.PROFILES,
    *network.PROFILES,
    *containers.PROFILES,
    *system.PROFILES,
]


def user_profile_dir() -> Path:
    """Where a user's own profiles live, honouring XDG_CONFIG_HOME."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "gamaxsene" / "profiles"


def load_user_profiles() -> list[Profile]:
    """Import every .py file in the user profile directory.

    A broken personal profile must never stop the tool working, so each file
    is loaded independently and failures are skipped.
    """
    directory = user_profile_dir()
    if not directory.is_dir():
        return []

    import importlib.util

    found: list[Profile] = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"_gx_profile_{path.stem}", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            continue
        profile = getattr(module, "PROFILE", None)
        if isinstance(profile, Profile):
            found.append(profile)
        for extra in getattr(module, "PROFILES", []) or []:
            if isinstance(extra, Profile):
                found.append(extra)
    return found


def all_profiles(include_user: bool = True) -> list[Profile]:
    """Built-in profiles, with the user's own taking precedence."""
    user = load_user_profiles() if include_user else []
    return [*user, *BUILTIN]


def by_name(name: str, include_user: bool = True) -> Profile | None:
    """Look a profile up for --as, tolerating 'docker ps' and 'docker-ps'."""
    wanted = name.strip().lower().replace("_", " ").replace("-", " ")
    for profile in all_profiles(include_user):
        if profile.name.lower().replace("-", " ") == wanted:
            return profile
    # Allow a prefix, so --as docker finds "docker ps".
    for profile in all_profiles(include_user):
        if profile.name.lower().startswith(wanted):
            return profile
    return None


def names(include_user: bool = True) -> list[str]:
    return sorted(p.name for p in all_profiles(include_user))


def match(headers: list[str], include_user: bool = True) -> Profile | None:
    """The best profile for these headers, or None."""
    candidates = [p for p in all_profiles(include_user) if p.matches(headers)]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.score)
