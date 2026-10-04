"""`barem help` -- run the first-try diagnostics and report what is off.

When something is wrong on a machine, the first few minutes are always the
same handful of commands: is the disk full, is memory gone, did a unit fail,
is there a default route, does DNS answer. This runs that list and reports
only what is actually wrong, so the answer is one screen instead of ten
commands.

Every check is read-only, needs no root, and is given a short timeout, so
running this can never make a bad situation worse. A check whose command is
missing reports `skipped` rather than failing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

from .table.humanize import human_size
from .table.model import Column, Kind, Table

#: Each check gets this long before it is abandoned. A hung NFS mount must
#: not hang the diagnosis.
TIMEOUT = 4.0

OK, WARN, BAD, SKIP = "ok", "warn", "bad", "skipped"

#: Handed to a judge when a `missing_is_fine` file is not there, so an
#: absent file and a present but empty one stay distinguishable.
MISSING = "<barem:file-absent>"

#: Severity order, for sorting the report worst-first.
RANK = {BAD: 0, WARN: 1, SKIP: 3, OK: 2}

#: How many "next:" suggestions to print. A machine where everything is on
#: fire does not need fifteen of them.
MAX_FOLLOW_UPS = 3


@dataclass
class Result:
    key: str
    title: str
    status: str
    detail: str = ""
    #: The command a reader should run themselves to see the full picture.
    follow_up: str = ""


@dataclass
class Check:
    """One diagnostic: where to get the data, and how to judge it."""

    key: str
    title: str
    #: Command to run. Missing executable means the check is skipped.
    argv: list[str] = field(default_factory=list)
    #: Or a file to read instead, which needs no subprocess at all.
    path: str = ""
    #: (text) -> (status, detail)
    judge: Callable[[str], tuple[str, str]] = lambda _text: (SKIP, "")
    follow_up: str = ""
    #: When the file simply not being there is itself the answer, as with
    #: /var/run/reboot-required, whose absence means no reboot is pending.
    missing_is_fine: bool = False


# -- gathering ---------------------------------------------------------------


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _run(argv: list[str]) -> str | None:
    """Run a command and return its output, or None if it cannot be run."""
    if not argv or shutil.which(argv[0]) is None:
        return None
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # Some of these report useful output on a non-zero exit, so the text is
    # what matters, not the status.
    return done.stdout + (done.stderr if not done.stdout else "")


def gather(check: Check) -> str | None:
    if not check.path:
        return _run(check.argv)
    text = _read(check.path)
    if text is None and check.missing_is_fine:
        return MISSING
    return text


def run_checks(
    checks: list[Check] | None = None,
    collect: Callable[[Check], str | None] | None = None,
) -> list[Result]:
    """Run every check and return its result.

    `collect` is injectable so the tests can feed known command output
    instead of depending on the machine they run on.
    """
    checks = CHECKS if checks is None else checks
    collect = collect or gather
    results: list[Result] = []
    for check in checks:
        text = collect(check)
        if text is None:
            what = check.path or (check.argv[0] if check.argv else "?")
            results.append(Result(check.key, check.title, SKIP, f"{what} unavailable"))
            continue
        try:
            status, detail = check.judge(text)
        except Exception as error:  # a broken check must not break the report
            status, detail = SKIP, f"check failed ({type(error).__name__})"
        results.append(Result(check.key, check.title, status, detail, check.follow_up))
    return results


# -- the judges --------------------------------------------------------------


#: Mount points whose being full is normal and not worth reporting.
UNINTERESTING_MOUNTS = ("/dev", "/sys", "/proc", "/run/user", "/snap", "/var/lib/snapd")


def _df_rows(text: str) -> list[tuple[str, int]]:
    """(mount point, percent) from df output.

    The percent column is found by its header rather than by position, since
    `df -P` and `df -Pi` name it differently (Capacity, IUse%) and a fixed
    index misreads anything that does not match GNU coreutils exactly. The
    mount point is everything after that column, which keeps a path with a
    space in it whole.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].split()
    pct_index = next(
        (i for i, h in enumerate(header) if h.endswith("%") or h.lower() == "capacity"),
        None,
    )
    if pct_index is None:
        return []

    rows: list[tuple[str, int]] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) <= pct_index:
            continue
        raw = parts[pct_index].rstrip("%")
        if not raw.isdigit():
            continue
        mount = " ".join(parts[pct_index + 1 :]) or parts[0]
        if mount.startswith(UNINTERESTING_MOUNTS):
            continue
        rows.append((mount, int(raw)))
    return rows


def _judge_df(text: str) -> tuple[str, str]:
    """Disk space. 90% full is the line, 80% is worth watching."""
    rows = _df_rows(text)
    if not rows:
        return SKIP, "could not read df output"
    worst = sorted(rows, key=lambda r: -r[1])
    full = [f"{n} {p}%" for n, p in worst if p >= 90]
    high = [f"{n} {p}%" for n, p in worst if 80 <= p < 90]
    if full:
        return BAD, ", ".join(full[:3])
    if high:
        return WARN, ", ".join(high[:3])
    return OK, f"worst {worst[0][1]}% ({worst[0][0]})"


def _judge_inodes(text: str) -> tuple[str, str]:
    """Inodes run out while df still shows free space, so writes fail oddly."""
    rows = _df_rows(text)
    if not rows:
        return SKIP, "could not read df output"
    worst = sorted(rows, key=lambda r: -r[1])
    full = [f"{n} {p}%" for n, p in worst if p >= 90]
    if full:
        return BAD, "inodes exhausted: " + ", ".join(full[:3])
    return OK, f"worst {worst[0][1]}% ({worst[0][0]})"


def _meminfo(text: str) -> dict[str, int]:
    values = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[key.strip()] = int(parts[0]) * 1024  # kB -> bytes
    return values


def _judge_memory(text: str) -> tuple[str, str]:
    mem = _meminfo(text)
    total, available = mem.get("MemTotal"), mem.get("MemAvailable")
    if not total or available is None:
        return SKIP, "could not read MemTotal/MemAvailable"
    share = available / total * 100
    detail = f"{human_size(available)} of {human_size(total)} available ({share:.0f}%)"
    if share < 5:
        return BAD, detail
    if share < 15:
        return WARN, detail
    return OK, detail


def _judge_swap(text: str) -> tuple[str, str]:
    mem = _meminfo(text)
    total, free = mem.get("SwapTotal"), mem.get("SwapFree")
    if not total:
        return OK, "no swap configured"
    used = total - (free or 0)
    share = used / total * 100
    detail = f"{human_size(used)} of {human_size(total)} used ({share:.0f}%)"
    # Swap in use is not itself a fault, but heavy use with little left is.
    if share >= 80:
        return WARN, detail
    return OK, detail


def _judge_load(text: str) -> tuple[str, str]:
    parts = text.split()
    if not parts:
        return SKIP, "could not read /proc/loadavg"
    load1 = float(parts[0])
    cores = os.cpu_count() or 1
    detail = f"{load1:.2f} over {cores} core{'s' if cores != 1 else ''}"
    if load1 > cores * 2:
        return BAD, detail
    if load1 > cores:
        return WARN, detail
    return OK, detail


def _judge_failed_units(text: str) -> tuple[str, str]:
    units = [line.split()[0] for line in text.splitlines() if line.strip() and "●" not in line]
    units = [u for u in units if u.endswith((".service", ".timer", ".mount", ".socket"))]
    if units:
        return BAD, ", ".join(units[:3]) + (f" (+{len(units) - 3})" if len(units) > 3 else "")
    return OK, "none"


def _judge_readonly(text: str) -> tuple[str, str]:
    """A filesystem remounted read-only is the classic silent outage."""
    bad = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[2] not in ("ext2", "ext3", "ext4", "xfs", "btrfs"):
            continue
        if "ro" in parts[3].split(","):
            bad.append(parts[1])
    if bad:
        return BAD, "read-only: " + ", ".join(bad)
    return OK, "all writable"


def _judge_oom(text: str) -> tuple[str, str]:
    hits = re.findall(r"Killed process (\d+) \(([^)]+)\)", text)
    if hits:
        names = ", ".join(dict.fromkeys(name for _pid, name in hits))
        return BAD, f"OOM killer hit: {names}"
    if re.search(r"out of memory", text, re.IGNORECASE):
        return WARN, "out-of-memory messages in the log"
    return OK, "none this boot"


def _judge_kernel_errors(text: str) -> tuple[str, str]:
    lines = [line for line in text.splitlines() if line.strip()]
    hard = [line for line in lines if re.search(r"I/O error|EXT4-fs error|XFS .*error", line)]
    if hard:
        return BAD, hard[-1][-70:].strip()
    if lines:
        return WARN, f"{len(lines)} error-level kernel message(s)"
    return OK, "none this boot"


def _judge_route(text: str) -> tuple[str, str]:
    if "default" in text:
        first = next((line for line in text.splitlines() if "default" in line), "")
        return OK, first.strip()[:70]
    return BAD, "no default route"


def _judge_dns(text: str) -> tuple[str, str]:
    if text.strip():
        return OK, text.split()[0] if text.split() else "resolves"
    return BAD, "no answer for the test name"


def _judge_clock(text: str) -> tuple[str, str]:
    if re.search(r"NTPSynchronized=yes|System clock synchronized: yes", text):
        return OK, "synchronised"
    if re.search(r"NTPSynchronized=no|System clock synchronized: no", text):
        # A wrong clock breaks TLS and tokens, and is easy to miss.
        return WARN, "clock not synchronised"
    return SKIP, "could not determine"


def _judge_reboot(text: str) -> tuple[str, str]:
    """/var/run/reboot-required exists only when one is pending.

    `missing_is_fine` hands the judge a sentinel when the file is absent, so
    an absent file reads as "no reboot needed" while a present but empty one
    is still treated as pending.
    """
    return (OK, "not required") if text == MISSING else (WARN, "a reboot is pending")


def _judge_zombies(text: str) -> tuple[str, str]:
    count = sum(1 for line in text.splitlines() if line.strip().startswith("Z"))
    if count > 10:
        return WARN, f"{count} zombie processes"
    return OK, "none" if not count else f"{count} zombie process(es)"


def _judge_file_descriptors(text: str) -> tuple[str, str]:
    parts = text.split()
    if len(parts) < 3:
        return SKIP, "could not read /proc/sys/fs/file-nr"
    allocated, _free, maximum = (int(parts[0]), int(parts[1]), int(parts[2]))
    share = allocated / maximum * 100 if maximum else 0
    detail = f"{allocated:,} of {maximum:,} ({share:.0f}%)"
    if share >= 80:
        return BAD, detail
    if share >= 60:
        return WARN, detail
    return OK, detail


# -- the list ----------------------------------------------------------------

CHECKS: list[Check] = [
    Check(
        "disk",
        "disk space",
        argv=["df", "-P"],
        judge=_judge_df,
        follow_up="df -h | barem --sort -use%",
    ),
    Check("inodes", "inodes", argv=["df", "-Pi"], judge=_judge_inodes, follow_up="df -i | barem"),
    Check(
        "memory",
        "memory",
        path="/proc/meminfo",
        judge=_judge_memory,
        follow_up="ps aux | barem --sort -%mem --top 10",
    ),
    Check("swap", "swap", path="/proc/meminfo", judge=_judge_swap, follow_up="free -h | barem"),
    Check(
        "load",
        "load average",
        path="/proc/loadavg",
        judge=_judge_load,
        follow_up="ps aux | barem --sort -%cpu --top 10",
    ),
    Check(
        "units",
        "failed units",
        argv=["systemctl", "--failed", "--no-legend", "--plain"],
        judge=_judge_failed_units,
        follow_up="systemctl --failed | barem",
    ),
    Check(
        "readonly",
        "read-only mounts",
        path="/proc/mounts",
        judge=_judge_readonly,
        follow_up="findmnt | barem",
    ),
    Check(
        "oom",
        "out of memory",
        argv=["journalctl", "-k", "-b", "--no-pager", "-q", "-n", "500"],
        judge=_judge_oom,
        follow_up="journalctl -k -b --grep='out of memory'",
    ),
    Check(
        "kernel",
        "kernel errors",
        argv=["journalctl", "-k", "-b", "-p", "err", "--no-pager", "-q", "-n", "50"],
        judge=_judge_kernel_errors,
        follow_up="journalctl -k -b -p err",
    ),
    Check(
        "route",
        "default route",
        argv=["ip", "route", "show", "default"],
        judge=_judge_route,
        follow_up="ip -br a | barem",
    ),
    Check(
        "dns",
        "dns",
        argv=["getent", "hosts", "localhost"],
        judge=_judge_dns,
        follow_up="dig +short example.com",
    ),
    Check(
        "clock",
        "clock sync",
        argv=["timedatectl", "show", "-p", "NTPSynchronized"],
        judge=_judge_clock,
        follow_up="timedatectl",
    ),
    Check(
        "reboot",
        "reboot pending",
        path="/var/run/reboot-required",
        judge=_judge_reboot,
        missing_is_fine=True,
        follow_up="cat /var/run/reboot-required.pkgs",
    ),
    Check(
        "zombies",
        "zombie processes",
        argv=["ps", "-eo", "stat"],
        judge=_judge_zombies,
        follow_up="ps -eo pid,ppid,stat,comm | barem --where 'stat ~ ^Z'",
    ),
    Check(
        "fds",
        "open file descriptors",
        path="/proc/sys/fs/file-nr",
        judge=_judge_file_descriptors,
        follow_up="lsof | barem --top 20",
    ),
]


# -- reporting ---------------------------------------------------------------


def build_table(results: list[Result], show_all: bool = False) -> Table:
    """Turn the results into a Table, so the renderer handles the rest."""
    shown = results if show_all else [r for r in results if r.status != OK]
    shown = sorted(shown, key=lambda r: (RANK.get(r.status, 9), r.title))

    columns = [
        Column("check", "CHECK", Kind.TEXT, priority=1, identity=True, min_width=12),
        Column("status", "STATUS", Kind.STATUS, priority=1, min_width=7),
        Column("detail", "DETAIL", Kind.TEXT, priority=2, min_width=12),
    ]
    rows = [{"check": r.title, "status": r.status, "detail": r.detail} for r in shown]

    bad = sum(1 for r in results if r.status == BAD)
    warn = sum(1 for r in results if r.status == WARN)
    ok = sum(1 for r in results if r.status == OK)
    skipped = sum(1 for r in results if r.status == SKIP)

    parts = []
    if bad:
        parts.append(f"{bad} critical")
    if warn:
        parts.append(f"{warn} to watch")
    if not bad and not warn:
        parts.append("nothing wrong found")
    parts.append(f"{ok} passed")
    if skipped:
        parts.append(f"{skipped} skipped")
    summary = " · ".join(parts)
    if not show_all and (ok or skipped):
        summary += " · barem help --all shows every check"

    table = Table(columns=columns, rows=rows, name="barem help", summary=summary)
    # Point at the command worth running next -- but only for the worst few.
    # On a badly broken machine every check fires, and fifteen suggestions is
    # not a next step, it is another wall of text.
    problems = [r for r in shown if r.status in (BAD, WARN) and r.follow_up]
    for result in problems[:MAX_FOLLOW_UPS]:
        table.notes.append(f"next: {result.follow_up}")
    if len(problems) > MAX_FOLLOW_UPS:
        table.notes.append(f"...and {len(problems) - MAX_FOLLOW_UPS} more to look at")
    return table


def exit_code(results: list[Result]) -> int:
    """0 when clean, 1 when only warnings, 2 when something is critical."""
    if any(r.status == BAD for r in results):
        return 2
    if any(r.status == WARN for r in results):
        return 1
    return 0
