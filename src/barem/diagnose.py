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

import glob
import json
import os
import platform
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

#: How many likely causes to name. More than three is not an analysis.
MAX_INSIGHTS = 3

#: The areas a check belongs to. `barem help --area memory` narrows to one,
#: and the analysis below reads them to tell a story out of several results.
CPU, MEMORY, STORAGE, NETWORK, SYSTEM, SECURITY = (
    "cpu",
    "memory",
    "storage",
    "network",
    "system",
    "security",
)
AREAS = (CPU, MEMORY, STORAGE, NETWORK, SYSTEM, SECURITY)

#: Sources that are read directly rather than run. Kept in one place so a
#: test can point the whole module at a fixture directory.
PROC = "/proc"
SYS = "/sys"


@dataclass
class Result:
    key: str
    title: str
    status: str
    detail: str = ""
    #: The command a reader should run themselves to see the full picture.
    follow_up: str = ""
    area: str = SYSTEM
    #: What this check looks at and where its thresholds are, for --explain.
    about: str = ""


@dataclass
class Check:
    """One diagnostic: where to get the data, and how to judge it."""

    key: str
    title: str
    #: Command to run. Missing executable means the check is skipped.
    argv: list[str] = field(default_factory=list)
    #: Or a file to read instead, which needs no subprocess at all.
    path: str = ""
    #: Or several files, whose contents arrive joined by newlines in this
    #: order -- a count and its maximum usually live in two files.
    paths: list[str] = field(default_factory=list)
    #: Or every file matching a pattern, sorted, for the per-device and
    #: per-zone trees under /sys where the count is not known in advance.
    glob: str = ""
    #: (text) -> (status, detail)
    judge: Callable[[str], tuple[str, str]] = lambda _text: (SKIP, "")
    follow_up: str = ""
    #: When the file simply not being there is itself the answer, as with
    #: /var/run/reboot-required, whose absence means no reboot is pending.
    missing_is_fine: bool = False
    area: str = SYSTEM
    #: One line on what is measured and where the line is drawn, for
    #: `barem help --explain`. A check nobody can interpret is not a check.
    about: str = ""


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


def _read_all(paths: list[str]) -> str | None:
    """Several files as one text, in the order given.

    Every one of them has to be there: a count without its maximum says
    nothing, so a half-read is reported as unavailable rather than judged.
    """
    out = []
    for path in paths:
        text = _read(path)
        if text is None:
            return None
        out.append(text.strip())
    return chr(10).join(out)


def _read_glob(pattern: str) -> str | None:
    """Every file matching a pattern, as `path: contents` lines.

    The judge needs to know which file each value came from -- one hot
    thermal zone out of nine is a different report from all nine being warm.
    """
    matches = sorted(glob.glob(pattern))
    if not matches:
        return None
    out = []
    for path in matches:
        text = _read(path)
        if text is not None:
            out.append(f"{path}: {text.strip()}")
    return chr(10).join(out) if out else None


def gather(check: Check) -> str | None:
    if check.glob:
        return _read_glob(check.glob)
    if check.paths:
        return _read_all(check.paths)
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
            what = (
                check.glob
                or check.path
                or (check.paths[0] if check.paths else "")
                or (check.argv[0] if check.argv else "?")
            )
            results.append(
                Result(
                    check.key,
                    check.title,
                    SKIP,
                    f"{what} unavailable",
                    area=check.area,
                    about=check.about,
                )
            )
            continue
        try:
            status, detail = check.judge(text)
        except Exception as error:  # a broken check must not break the report
            status, detail = SKIP, f"check failed ({type(error).__name__})"
        results.append(
            Result(
                check.key,
                check.title,
                status,
                detail,
                check.follow_up,
                area=check.area,
                about=check.about,
            )
        )
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


# -- pressure, saturation and contention -------------------------------------


def _psi(text: str) -> dict[str, dict[str, float]]:
    """Parse /proc/pressure/*: {"some": {"avg10": .., "avg60": ..}, "full": ..}

    Pressure stall information is the kernel saying how much time tasks spent
    waiting for a resource, which is a far better answer to "is it slow" than
    a utilisation figure: a disk can be 100% busy and fine, or 20% busy with
    everything blocked behind it.
    """
    out: dict[str, dict[str, float]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] not in ("some", "full"):
            continue
        values = {}
        for part in parts[1:]:
            key, _, raw = part.partition("=")
            try:
                values[key] = float(raw)
            except ValueError:
                continue
        out[parts[0]] = values
    return out


def _trend(values: dict[str, float]) -> str:
    """ "rising", "easing" or "steady", from the three PSI windows.

    One number cannot say whether a machine is recovering or getting worse,
    and that is usually the thing you actually want to know.
    """
    short, long = values.get("avg10"), values.get("avg300")
    if short is None or long is None:
        return ""
    if short > long * 1.5 and short - long > 5:
        return "rising"
    if long > short * 1.5 and long - short > 5:
        return "easing"
    return "steady"


def _judge_pressure(text: str, resource: str, warn: float, crit: float) -> tuple[str, str]:
    """Shared judgement for the three pressure files."""
    psi = _psi(text)
    some = psi.get("some")
    if not some or "avg60" not in some:
        return SKIP, "no pressure information (needs a kernel with PSI)"
    minute = some["avg60"]
    trend = _trend(some)
    detail = f"{minute:.0f}% of the last minute waiting on {resource}"
    if trend and trend != "steady":
        detail += f", {trend}"
    if minute >= crit:
        return BAD, detail
    if minute >= warn:
        return WARN, detail
    return OK, detail


def _judge_psi_cpu(text: str) -> tuple[str, str]:
    return _judge_pressure(text, "cpu", 25.0, 50.0)


def _judge_psi_io(text: str) -> tuple[str, str]:
    # I/O pressure bites sooner than the other two: a tenth of the time
    # blocked on disk is already a machine that feels broken to use.
    return _judge_pressure(text, "disk", 10.0, 30.0)


def _judge_psi_memory(text: str) -> tuple[str, str]:
    # Any sustained memory pressure means reclaim is working for its living,
    # and the OOM killer is the step after that.
    return _judge_pressure(text, "memory", 5.0, 20.0)


CPU_TIME_FIELDS = (
    "user",
    "nice",
    "system",
    "idle",
    "iowait",
    "irq",
    "softirq",
    "steal",
    "guest",
    "guest_nice",
)


def _cpu_times(text: str) -> dict[str, float]:
    """The aggregate cpu line of /proc/stat, as shares of the total."""
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == "cpu":
            numbers = [float(p) for p in parts[1:] if p.isdigit()]
            total = sum(numbers) or 1.0
            return {n: v / total * 100 for n, v in zip(CPU_TIME_FIELDS, numbers)}
    return {}


def _judge_steal(text: str) -> tuple[str, str]:
    """Steal time: the hypervisor running someone else instead of you.

    On a VM this is the difference between "my application is slow" and "the
    host is oversubscribed and there is nothing in this machine to fix".
    """
    times = _cpu_times(text)
    if "steal" not in times:
        return SKIP, "could not read /proc/stat"
    steal = times["steal"]
    detail = f"{steal:.1f}% of cpu time taken by the hypervisor since boot"
    if steal >= 10:
        return BAD, detail
    if steal >= 5:
        return WARN, detail
    return OK, "none" if steal < 0.5 else detail


def _judge_iowait(text: str) -> tuple[str, str]:
    """Time the cpu spent with nothing to do but wait for a disk."""
    times = _cpu_times(text)
    if "iowait" not in times:
        return SKIP, "could not read /proc/stat"
    iowait = times["iowait"]
    detail = f"{iowait:.1f}% of cpu time waiting for disk since boot"
    if iowait >= 25:
        return BAD, detail
    if iowait >= 10:
        return WARN, detail
    return OK, detail


def _judge_dirty(text: str) -> tuple[str, str]:
    """Pages written but not yet on disk. A large, stuck pile means trouble."""
    mem = _meminfo(text)
    dirty, writeback = mem.get("Dirty"), mem.get("Writeback")
    if dirty is None:
        return SKIP, "could not read Dirty from /proc/meminfo"
    total = dirty + (writeback or 0)
    detail = f"{human_size(total)} waiting to be written"
    # Writeback is the part the kernel is actively flushing; a gigabyte of it
    # means the flush is not keeping up with what is being written.
    if (writeback or 0) > 1024**3:
        return WARN, detail + f", {human_size(writeback or 0)} in flight"
    if total > 4 * 1024**3:
        return WARN, detail
    return OK, detail


def _judge_dstate(text: str) -> tuple[str, str]:
    """Processes in uninterruptible sleep: stuck in the kernel, usually on I/O.

    These cannot be killed and do not respond, so a handful of them is the
    signature of a disk or an NFS mount that has stopped answering.
    """
    names = []
    for line in text.splitlines()[1:]:
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].startswith("D"):
            names.append(parts[1].strip())
    if not names:
        return OK, "none"
    unique = list(dict.fromkeys(names))
    detail = f"{len(names)} stuck in uninterruptible sleep: " + ", ".join(unique[:3])
    return (BAD if len(names) >= 5 else WARN), detail


# -- network -----------------------------------------------------------------


def _judge_conntrack(text: str) -> tuple[str, str]:
    """The connection tracking table, which drops packets silently when full.

    Reads the count and the maximum, in that order. A full table is one of
    the hardest outages to diagnose from inside the machine, because
    everything simply times out.
    """
    parts = text.split()
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return SKIP, "could not read the conntrack table"
    count, maximum = int(parts[0]), int(parts[1])
    if maximum <= 0:
        return SKIP, "conntrack maximum is zero"
    share = count / maximum * 100
    detail = f"{count:,} of {maximum:,} tracked connections ({share:.0f}%)"
    if share >= 90:
        return BAD, detail
    if share >= 75:
        return WARN, detail
    return OK, detail


def _netdev(text: str) -> list[tuple[str, int, int, int]]:
    """(interface, packets, errors, drops) from /proc/net/dev, both directions."""
    out = []
    for line in text.splitlines():
        name, separator, rest = line.partition(":")
        name = name.strip()
        if not separator or not name or name == "lo":
            continue
        numbers = rest.split()
        if len(numbers) < 16:
            continue
        try:
            values = [int(n) for n in numbers[:16]]
        except ValueError:
            continue
        out.append((name, values[1] + values[9], values[2] + values[10], values[3] + values[11]))
    return out


def _judge_netdev(text: str) -> tuple[str, str]:
    """Interface errors and drops, as a share of what went through.

    A raw counter means nothing -- a machine up for a year will have dropped
    something. What matters is the proportion, so the judgement is a rate.
    """
    rows = _netdev(text)
    if not rows:
        return SKIP, "no interfaces in /proc/net/dev"
    worst, worst_rate = "", 0.0
    for name, packets, errors, drops in rows:
        if packets < 1000:  # too little traffic for a rate to mean anything
            continue
        rate = (errors + drops) / packets * 100
        if rate > worst_rate:
            worst, worst_rate = name, rate
    if not worst:
        return OK, "no interface has enough traffic to judge"
    detail = f"{worst}: {worst_rate:.2f}% of packets dropped or in error"
    if worst_rate >= 1:
        return BAD, detail
    if worst_rate >= 0.1:
        return WARN, detail
    return OK, detail


def _netstat_counters(text: str) -> dict[str, int]:
    """/proc/net/netstat is pairs of lines: names, then values."""
    counters: dict[str, int] = {}
    lines = text.splitlines()
    for index in range(0, len(lines) - 1, 2):
        names = lines[index].split()
        values = lines[index + 1].split()
        if not names or len(names) != len(values):
            continue
        for name, value in zip(names[1:], values[1:]):
            try:
                counters[name] = int(value)
            except ValueError:
                continue
    return counters


def _judge_tcp(text: str) -> tuple[str, str]:
    """Listen-queue overflows and retransmissions.

    An overflowing accept queue is a server refusing connections while
    looking perfectly healthy from the outside, and it is invisible unless
    you know to look at this counter.
    """
    counters = _netstat_counters(text)
    if not counters:
        return SKIP, "could not read tcp counters"
    overflows = counters.get("ListenOverflows", 0)
    drops = counters.get("ListenDrops", 0)
    retrans = counters.get("TCPSynRetrans", 0)
    segments = counters.get("InSegs", 0) or counters.get("TCPHPHits", 0)

    if overflows:
        return BAD, f"{overflows:,} connections refused by a full accept queue"
    if drops > 100:
        return WARN, f"{drops:,} connections dropped before being accepted"
    if segments and retrans and retrans / segments * 100 >= 5:
        return WARN, f"{retrans / segments * 100:.1f}% of connection attempts retransmitted"
    return OK, "no listen-queue overflows"


def _judge_sockets(text: str) -> tuple[str, str]:
    """Socket counts, for the orphan and time-wait piles that exhaust ports."""
    counters: dict[str, int] = {}
    for line in text.splitlines():
        head, separator, rest = line.partition(":")
        if not separator:
            continue
        parts = rest.split()
        for index in range(0, len(parts) - 1, 2):
            if parts[index + 1].isdigit():
                counters[f"{head.strip()}.{parts[index]}"] = int(parts[index + 1])
    inuse = counters.get("TCP.inuse")
    if inuse is None:
        return SKIP, "could not read /proc/net/sockstat"
    tw = counters.get("TCP.tw", 0)
    orphan = counters.get("TCP.orphan", 0)
    detail = f"{inuse:,} in use, {tw:,} closing, {orphan:,} orphaned"
    # The default ephemeral range is about 28,000 ports, so a time-wait pile
    # anywhere near that means new outbound connections start failing.
    if tw > 20000:
        return WARN, detail + " -- close to exhausting the ephemeral ports"
    if orphan > 1000:
        return WARN, detail
    return OK, detail


#: What `hostname -f` says when it cannot resolve the name. It writes these
#: to stderr and still exits zero on some systems, so the text is what tells
#: us, not the exit status.
RESOLVER_FAILURES = (
    "name or service not known",
    "temporary failure in name resolution",
    "unknown host",
    "host name lookup failure",
    "no address associated",
)


def _judge_hostname(text: str) -> tuple[str, str]:
    """The machine's own name has to resolve.

    When it does not, sudo waits for a DNS timeout on every single command,
    and nothing else on the machine looks wrong at all.
    """
    answer = text.strip()
    lowered = answer.lower()
    if not answer or any(failure in lowered for failure in RESOLVER_FAILURES):
        return WARN, "the machine's own hostname does not resolve (sudo will be slow)"
    return OK, "resolves to " + answer.split()[0]


#: Ports whose service holds data and should almost never answer the world.
RISKY_PORTS = {
    "3306": "mysql",
    "5432": "postgres",
    "6379": "redis",
    "27017": "mongodb",
    "9200": "elasticsearch",
    "11211": "memcached",
    "2375": "docker api",
    "5984": "couchdb",
    "9042": "cassandra",
}


def _judge_exposed(text: str) -> tuple[str, str]:
    """Data stores listening on every interface rather than on loopback.

    This is the mistake that puts a database on the public internet, and the
    machine gives no sign of it: the service works perfectly.
    """
    exposed = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        address, _, port = local.rpartition(":")
        if port in RISKY_PORTS and address.strip("[]") in ("0.0.0.0", "*", "::", ""):
            exposed.append(f"{RISKY_PORTS[port]} on {local}")
    if exposed:
        found = list(dict.fromkeys(exposed))
        return WARN, "reachable from any network: " + ", ".join(found[:3])
    return OK, "no data store bound to every interface"


# -- system state ------------------------------------------------------------


def _judge_system_state(text: str) -> tuple[str, str]:
    """What systemd itself thinks of the machine."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    state = lines[0] if lines else ""
    if state == "running":
        return OK, "running"
    if state in ("degraded", "maintenance", "stopping"):
        return BAD, f"systemd reports the system as {state}"
    if state in ("starting", "initializing"):
        return WARN, f"still {state}"
    return SKIP, "could not determine the system state"


def _judge_uptime(text: str) -> tuple[str, str]:
    """How long the machine has been up.

    Never a fault on its own, but a boot ten minutes ago changes how you read
    everything else on this page, and the analysis below says so.
    """
    parts = text.split()
    if not parts:
        return SKIP, "could not read /proc/uptime"
    try:
        seconds = float(parts[0])
    except ValueError:
        return SKIP, "could not read /proc/uptime"
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        pretty = f"{days}d {hours}h"
    elif hours:
        pretty = f"{hours}h {minutes}m"
    else:
        pretty = f"{minutes}m"
    return OK, f"up {pretty}"


def _version_key(text: str) -> tuple:
    """Sort kernel versions the way a human reads them, not as strings.

    Otherwise 6.8.0-10 sorts before 6.8.0-9, and the check reports a reboot
    that is not needed.
    """
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"[.\-]", text) if p)


def _judge_kernel_version(text: str) -> tuple[str, str]:
    """A newer kernel installed than the one running means a pending reboot.

    Debian's /var/run/reboot-required covers its own upgrades; this catches
    the same thing on every distribution, by comparing what is in /boot with
    what is actually running.
    """
    installed = []
    for line in text.splitlines():
        path, _, _ = line.partition(":")
        version = path.rsplit("/", 1)[-1].partition("-")[2]
        if version:
            installed.append(version)
    if not installed:
        return SKIP, "no kernels found in /boot"
    running = platform.release()
    newest = max(installed, key=_version_key)
    try:
        newer = _version_key(newest) > _version_key(running)
    except TypeError:  # versions that will not compare: say nothing rather than guess
        return SKIP, "could not compare the installed kernels"
    if not newer:
        return OK, f"running the newest installed ({running})"
    return WARN, f"{newest} installed, {running} running -- reboot to take it up"


def _judge_crashes(text: str) -> tuple[str, str]:
    """Programs that dumped core recently."""
    lines = [line for line in text.splitlines() if line.strip()]
    lines = [line for line in lines if not line.split()[0].upper().startswith("TIME")]
    if not lines:
        return OK, "none recorded"
    names = []
    for line in lines:
        parts = line.split()
        # The executable is the last column. Counting from the left would
        # land on the pid, because the TIME column is five tokens wide.
        if len(parts) >= 5 and "/" in parts[-1]:
            names.append(parts[-1].rsplit("/", 1)[-1])
    unique = list(dict.fromkeys(names)) or ["unnamed"]
    return WARN, f"{len(lines)} crash(es): " + ", ".join(unique[:3])


def _judge_journal_size(text: str) -> tuple[str, str]:
    """How much disk the journal is holding on to."""
    match = re.search(r"take up ([\d.]+)([KMGT])", text)
    if not match:
        return SKIP, "could not read the journal size"
    size = float(match.group(1))
    unit = match.group(2)
    bytes_ = size * {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}[unit]
    detail = f"{size:g}{unit} of logs on disk"
    if bytes_ > 8 * 1024**3:
        return WARN, detail + " -- journalctl --vacuum-size=1G will reclaim it"
    return OK, detail


def _judge_updates(text: str) -> tuple[str, str]:
    """Pending package updates, and how many of them are security ones."""
    total = re.search(r"(\d+) (?:package|update)s? can be", text) or re.search(
        r"^(\d+) updates", text, re.MULTILINE
    )
    if not total:
        return SKIP, "could not read the update count"
    count = int(total.group(1))
    security = re.search(r"(\d+) of these updates (?:are|is) (?:a )?security", text)
    if security and int(security.group(1)):
        return WARN, f"{count} updates pending, {security.group(1)} of them security"
    if count:
        return OK, f"{count} updates pending"
    return OK, "up to date"


def _judge_auth_failures(text: str) -> tuple[str, str]:
    """Repeated failed logins: a misconfigured client, or somebody knocking."""
    failures = re.findall(r"Failed password for(?: invalid user)? (\S+)", text)
    invalid = re.findall(r"Invalid user (\S+)", text)
    total = len(failures) + len(invalid)
    if not total:
        return OK, "none this boot"
    names = list(dict.fromkeys(failures + invalid))
    detail = f"{total} failed logins this boot, for " + ", ".join(names[:3])
    if total >= 50:
        return WARN, detail + " -- looks like a brute force"
    if total >= 10:
        return WARN, detail
    return OK, detail


# -- the list ----------------------------------------------------------------

CHECKS: list[Check] = [
    # -- storage ------------------------------------------------------------
    Check(
        "disk",
        "disk space",
        argv=["df", "-P"],
        judge=_judge_df,
        follow_up="df -h | barem --sort -use%",
        area=STORAGE,
        about="every mounted filesystem; 80% full is worth watching, 90% is critical",
    ),
    Check(
        "inodes",
        "inodes",
        argv=["df", "-Pi"],
        judge=_judge_inodes,
        follow_up="df -i | barem",
        area=STORAGE,
        about="inodes run out while df still shows free space; 90% used is critical",
    ),
    Check(
        "readonly",
        "read-only mounts",
        path="/proc/mounts",
        judge=_judge_readonly,
        follow_up="findmnt | barem",
        area=STORAGE,
        about="a filesystem the kernel remounted read-only after an error",
    ),
    Check(
        "psi_io",
        "disk pressure",
        path="/proc/pressure/io",
        judge=_judge_psi_io,
        follow_up="iostat -xz 2 | barem",
        area=STORAGE,
        about="share of the last minute tasks spent blocked on disk; 10% warns, 30% is critical",
    ),
    Check(
        "iowait",
        "io wait",
        path="/proc/stat",
        judge=_judge_iowait,
        follow_up="iostat -xz 2",
        area=STORAGE,
        about="cpu time spent waiting for disk since boot; 10% warns, 25% is critical",
    ),
    Check(
        "dstate",
        "stuck processes",
        argv=["ps", "-eo", "stat,comm"],
        judge=_judge_dstate,
        follow_up="ps -eo pid,stat,wchan:20,comm | barem --where 'stat ~ ^D'",
        area=STORAGE,
        about="processes in uninterruptible sleep, the signature of a disk or NFS mount that "
        "stopped answering",
    ),
    Check(
        "journal",
        "journal size",
        argv=["journalctl", "--disk-usage"],
        judge=_judge_journal_size,
        follow_up="journalctl --vacuum-size=1G",
        area=STORAGE,
        about="disk held by the systemd journal; over 8G is worth reclaiming",
    ),
    # -- memory -------------------------------------------------------------
    Check(
        "memory",
        "memory",
        path="/proc/meminfo",
        judge=_judge_memory,
        follow_up="ps aux | barem --sort -%mem --top 10",
        area=MEMORY,
        about="MemAvailable against MemTotal; under 15% warns, under 5% is critical",
    ),
    Check(
        "swap",
        "swap",
        path="/proc/meminfo",
        judge=_judge_swap,
        follow_up="free -h | barem",
        area=MEMORY,
        about="swap in use is not a fault, but 80% used with little left is",
    ),
    Check(
        "psi_memory",
        "memory pressure",
        path="/proc/pressure/memory",
        judge=_judge_psi_memory,
        follow_up="ps aux | barem --sort -%mem --top 10",
        area=MEMORY,
        about="share of the last minute spent reclaiming memory; 5% warns, 20% is critical",
    ),
    Check(
        "oom",
        "out of memory",
        argv=["journalctl", "-k", "-b", "--no-pager", "-q", "-n", "500"],
        judge=_judge_oom,
        follow_up="journalctl -k -b --grep='out of memory'",
        area=MEMORY,
        about="the kernel killing processes to free memory, this boot",
    ),
    Check(
        "dirty",
        "unwritten pages",
        path="/proc/meminfo",
        judge=_judge_dirty,
        follow_up="grep -E 'Dirty|Writeback' /proc/meminfo",
        area=MEMORY,
        about="pages written but not yet on disk; a large pile in flight means writeback is "
        "not keeping up",
    ),
    # -- cpu ----------------------------------------------------------------
    Check(
        "load",
        "load average",
        path="/proc/loadavg",
        judge=_judge_load,
        follow_up="ps aux | barem --sort -%cpu --top 10",
        area=CPU,
        about="one-minute load against the core count; above one per core warns, two is critical",
    ),
    Check(
        "psi_cpu",
        "cpu pressure",
        path="/proc/pressure/cpu",
        judge=_judge_psi_cpu,
        follow_up="ps aux | barem --sort -%cpu --top 10",
        area=CPU,
        about="share of the last minute tasks spent waiting for cpu; 25% warns, 50% is critical",
    ),
    Check(
        "steal",
        "hypervisor steal",
        path="/proc/stat",
        judge=_judge_steal,
        follow_up="vmstat 2 5",
        area=CPU,
        about="cpu time the hypervisor gave to someone else; 5% warns, 10% is critical, and "
        "nothing inside this machine can fix it",
    ),
    # -- network ------------------------------------------------------------
    Check(
        "route",
        "default route",
        argv=["ip", "route", "show", "default"],
        judge=_judge_route,
        follow_up="ip -br a | barem",
        area=NETWORK,
        about="a default route has to exist for anything off this machine to work",
    ),
    Check(
        "dns",
        "dns",
        argv=["getent", "hosts", "localhost"],
        judge=_judge_dns,
        follow_up="dig +short example.com",
        area=NETWORK,
        about="name resolution through the system resolver",
    ),
    Check(
        "hostname",
        "own hostname",
        argv=["hostname", "-f"],
        judge=_judge_hostname,
        follow_up="getent hosts $(hostname)",
        area=NETWORK,
        about="a machine whose own name does not resolve makes every sudo wait for a timeout",
    ),
    Check(
        "conntrack",
        "connection tracking",
        paths=[
            "/proc/sys/net/netfilter/nf_conntrack_count",
            "/proc/sys/net/netfilter/nf_conntrack_max",
        ],
        judge=_judge_conntrack,
        follow_up="conntrack -S",
        area=NETWORK,
        about="the firewall connection table, which drops packets silently when full; "
        "75% warns, 90% is critical",
    ),
    Check(
        "netdev",
        "interface errors",
        path="/proc/net/dev",
        judge=_judge_netdev,
        follow_up="ip -s link | barem",
        area=NETWORK,
        about="errors and drops as a share of packets carried; 0.1% warns, 1% is critical",
    ),
    Check(
        "tcp",
        "tcp health",
        path="/proc/net/netstat",
        judge=_judge_tcp,
        follow_up="ss -lti | barem",
        area=NETWORK,
        about="listen-queue overflows, which are connections refused by a server that looks "
        "perfectly healthy",
    ),
    Check(
        "sockets",
        "sockets",
        path="/proc/net/sockstat",
        judge=_judge_sockets,
        follow_up="ss -s",
        area=NETWORK,
        about="sockets in use, closing and orphaned; a large time-wait pile exhausts the "
        "ephemeral ports",
    ),
    # -- system -------------------------------------------------------------
    Check(
        "state",
        "system state",
        argv=["systemctl", "is-system-running"],
        judge=_judge_system_state,
        follow_up="systemctl status",
        area=SYSTEM,
        about="what systemd itself makes of the machine: running, degraded or in maintenance",
    ),
    Check(
        "units",
        "failed units",
        argv=["systemctl", "--failed", "--no-legend", "--plain"],
        judge=_judge_failed_units,
        follow_up="systemctl --failed | barem",
        area=SYSTEM,
        about="services, timers, mounts and sockets systemd could not start or keep running",
    ),
    Check(
        "kernel",
        "kernel errors",
        argv=["journalctl", "-k", "-b", "-p", "err", "--no-pager", "-q", "-n", "50"],
        judge=_judge_kernel_errors,
        follow_up="journalctl -k -b -p err",
        area=SYSTEM,
        about="error-level kernel messages this boot, with I/O and filesystem errors "
        "counted as critical",
    ),
    Check(
        "crashes",
        "recent crashes",
        argv=["coredumpctl", "--no-pager", "-q", "list", "--since", "-7d"],
        judge=_judge_crashes,
        follow_up="coredumpctl list --since -7d",
        area=SYSTEM,
        about="programs that dumped core in the last week",
    ),
    Check(
        "clock",
        "clock sync",
        argv=["timedatectl", "show", "-p", "NTPSynchronized"],
        judge=_judge_clock,
        follow_up="timedatectl",
        area=SYSTEM,
        about="an unsynchronised clock breaks TLS and tokens, and is easy to miss",
    ),
    Check(
        "uptime",
        "uptime",
        path="/proc/uptime",
        judge=_judge_uptime,
        follow_up="uptime",
        area=SYSTEM,
        about="how long the machine has been up; never a fault, but it changes how the rest "
        "of this page reads",
    ),
    Check(
        "zombies",
        "zombie processes",
        argv=["ps", "-eo", "stat"],
        judge=_judge_zombies,
        follow_up="ps -eo pid,ppid,stat,comm | barem --where 'stat ~ ^Z'",
        area=SYSTEM,
        about="processes whose parent never collected them; past ten, the parent is at fault",
    ),
    Check(
        "fds",
        "open file descriptors",
        path="/proc/sys/fs/file-nr",
        judge=_judge_file_descriptors,
        follow_up="lsof | barem --top 20",
        area=SYSTEM,
        about="file descriptors allocated against the system maximum; 60% warns, 80% is critical",
    ),
    Check(
        "reboot",
        "reboot pending",
        path="/var/run/reboot-required",
        judge=_judge_reboot,
        missing_is_fine=True,
        follow_up="cat /var/run/reboot-required.pkgs",
        area=SYSTEM,
        about="Debian and Ubuntu leave this file behind when an upgrade needs a reboot",
    ),
    Check(
        "kernel_version",
        "kernel version",
        glob="/boot/vmlinuz-*",
        judge=_judge_kernel_version,
        follow_up="uname -r; ls /boot/vmlinuz-*",
        area=SYSTEM,
        about="a kernel newer than the running one means the reboot has not happened yet, "
        "on any distribution",
    ),
    Check(
        "updates",
        "pending updates",
        path="/var/lib/update-notifier/updates-available",
        judge=_judge_updates,
        follow_up="apt list --upgradable",
        area=SYSTEM,
        about="packages waiting to be upgraded, and how many of those are security updates",
    ),
    # -- security -----------------------------------------------------------
    Check(
        "auth",
        "failed logins",
        argv=["journalctl", "-b", "--no-pager", "-q", "-n", "2000", "-t", "sshd"],
        judge=_judge_auth_failures,
        follow_up="journalctl -b -t sshd | barem",
        area=SECURITY,
        about="failed ssh logins this boot; fifty of them is somebody knocking, not a typo",
    ),
    Check(
        "exposed",
        "exposed services",
        argv=["ss", "-tlnH"],
        judge=_judge_exposed,
        follow_up="ss -tlnp | barem",
        area=SECURITY,
        about="databases and caches listening on every interface instead of on loopback",
    ),
]


# -- analysis ----------------------------------------------------------------
#
# A list of failing checks is not a diagnosis. Fifteen red rows on a machine
# that ran out of memory are one event seen fifteen ways, and the useful
# output is the sentence that names it. Each pattern below is a claim about a
# cause, the checks that have to agree before it is made, and what to do
# about it. Nothing here invents a finding: a pattern can only fire on checks
# that already failed on their own.


@dataclass
class Insight:
    """One likely cause, and the evidence for it."""

    headline: str
    #: Keys of the checks that led here, so the reader can see the working.
    evidence: list[str] = field(default_factory=list)
    #: What to do about it, when there is something obvious to do.
    advice: str = ""
    #: Insights are reported worst first, like the checks themselves.
    severity: str = WARN


@dataclass
class Pattern:
    """A named correlation: what has to be true, and what it means."""

    name: str
    #: Checks that must be failing (BAD or WARN) for this to fire.
    needs: tuple[str, ...]
    #: At least one of these must be failing too.
    any_of: tuple[str, ...] = ()
    headline: str = ""
    advice: str = ""
    severity: str = WARN
    #: Checks whose being healthy is part of the claim, as in "the load is
    #: not yours" requiring that the machine is not actually busy.
    unless: tuple[str, ...] = ()


PATTERNS: tuple[Pattern, ...] = (
    Pattern(
        "memory-exhaustion",
        needs=("memory",),
        any_of=("oom", "psi_memory", "swap"),
        headline="the machine is running out of memory",
        advice="find the process: ps aux | barem --sort -%mem --top 10",
        severity=BAD,
    ),
    Pattern(
        "disk-full-readonly",
        needs=("disk", "readonly"),
        headline="a filesystem filled up and the kernel remounted it read-only",
        advice="free space, then remount: mount -o remount,rw /",
        severity=BAD,
    ),
    Pattern(
        "storage-stalled",
        needs=("dstate",),
        any_of=("psi_io", "iowait"),
        headline="the storage has stopped keeping up, and processes are stuck on it",
        advice="find what they are waiting for: ps -eo pid,stat,wchan:20,comm | barem",
        severity=BAD,
    ),
    Pattern(
        "host-contention",
        needs=("steal",),
        any_of=("load", "psi_cpu"),
        headline="the load is the hypervisor's, not this machine's",
        advice="nothing here will fix it -- the host is oversubscribed",
        severity=WARN,
    ),
    Pattern(
        "cpu-saturated",
        needs=("load", "psi_cpu"),
        unless=("steal",),
        headline="the machine is genuinely busy, not waiting on anything",
        advice="find the process: ps aux | barem --sort -%cpu --top 10",
        severity=WARN,
    ),
    Pattern(
        "inodes-not-space",
        needs=("inodes",),
        unless=("disk",),
        headline="writes will fail although df still shows free space: the inodes are gone",
        advice="find the directory with the small files: du --inodes -x -d2 / | sort -rn | head",
        severity=BAD,
    ),
    Pattern(
        "network-dropping",
        needs=("conntrack",),
        headline="the connection tracking table is full, so new connections are dropped silently",
        advice="raise net.netfilter.nf_conntrack_max, or find what is opening them",
        severity=BAD,
    ),
    Pattern(
        "accept-queue-full",
        needs=("tcp",),
        headline="a server is refusing connections from a full accept queue while looking healthy",
        advice="find it: ss -lti | barem, then raise its backlog and somaxconn",
        severity=BAD,
    ),
    Pattern(
        "isolated",
        needs=("route", "dns"),
        headline="this machine cannot reach anything: no default route and no name resolution",
        advice="start at the link: ip -br a | barem",
        severity=BAD,
    ),
    Pattern(
        "swap-thrashing",
        needs=("swap", "psi_memory"),
        headline="memory has spilled into swap and the machine is thrashing",
        advice="this is slower than being out of memory outright; free some",
        severity=BAD,
    ),
    Pattern(
        "maintenance-pending",
        needs=("kernel_version",),
        any_of=("reboot", "updates"),
        headline="this machine is running an older kernel than the one installed",
        advice="schedule a reboot",
        severity=WARN,
    ),
)

#: A boot this recent changes how everything else on the page reads.
RECENT_BOOT_SECONDS = 3600


def _failing(results: dict[str, Result], key: str) -> bool:
    result = results.get(key)
    return result is not None and result.status in (BAD, WARN)


def _rebooted_recently(results: dict[str, Result]) -> bool:
    uptime = results.get("uptime")
    if uptime is None or uptime.status == SKIP:
        return False
    text = uptime.detail
    if "d " in text or "h " in text:
        return False
    minutes = re.search(r"(\d+)m", text)
    return bool(minutes) and int(minutes.group(1)) * 60 < RECENT_BOOT_SECONDS


def analyse(results: list[Result]) -> list[Insight]:
    """Read the results together and say what they add up to.

    Returns the likely causes, worst first. An empty list means the failures
    do not form a pattern anybody has named -- which is not the same as the
    machine being healthy, and is why this never replaces the table.
    """
    index = {r.key: r for r in results}
    found: list[Insight] = []

    for pattern in PATTERNS:
        if not all(_failing(index, key) for key in pattern.needs):
            continue
        if pattern.any_of and not any(_failing(index, key) for key in pattern.any_of):
            continue
        if any(_failing(index, key) for key in pattern.unless):
            continue
        evidence = list(pattern.needs)
        evidence += [key for key in pattern.any_of if _failing(index, key)]
        found.append(Insight(pattern.headline, evidence, pattern.advice, pattern.severity))

    # Context rather than a cause: a machine that booted minutes ago explains
    # counters that look clean and a journal that looks empty.
    if _rebooted_recently(index):
        crashed = [k for k in ("oom", "crashes", "kernel") if _failing(index, k)]
        if crashed:
            found.append(
                Insight(
                    "the machine rebooted within the hour, and something crashed before it did",
                    crashed,
                    "read the previous boot: journalctl -b -1 -p err",
                    BAD,
                )
            )
        else:
            found.append(
                Insight(
                    "the machine rebooted within the hour, so counters and logs are nearly empty",
                    ["uptime"],
                    "read the previous boot: journalctl -b -1 -p err",
                    WARN,
                )
            )

    found.sort(key=lambda i: RANK.get(i.severity, 9))
    return found


def verdict(results: list[Result]) -> str:
    """One word for the whole machine, for a script or a dashboard."""
    if any(r.status == BAD for r in results):
        return "critical"
    if any(r.status == WARN for r in results):
        return "degraded"
    return "healthy"


# -- reporting ---------------------------------------------------------------


def select(results: list[Result], area: str = "") -> list[Result]:
    """Narrow to one area, for `barem help --area memory`."""
    if not area:
        return results
    wanted = area.strip().lower()
    return [r for r in results if r.area == wanted]


def build_table(
    results: list[Result],
    show_all: bool = False,
    insights: list[Insight] | None = None,
) -> Table:
    """Turn the results into a Table, so the renderer handles the rest."""
    shown = results if show_all else [r for r in results if r.status != OK]
    shown = sorted(shown, key=lambda r: (RANK.get(r.status, 9), r.area, r.title))

    columns = [
        Column("check", "CHECK", Kind.TEXT, priority=1, identity=True, min_width=12),
        Column("area", "AREA", Kind.TEXT, priority=4, min_width=7),
        Column("status", "STATUS", Kind.STATUS, priority=1, min_width=7),
        Column("detail", "DETAIL", Kind.TEXT, priority=2, min_width=12),
    ]
    rows = [
        {"check": r.title, "area": r.area, "status": r.status, "detail": r.detail} for r in shown
    ]

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

    # The analysis goes above the follow-ups, because a reader who believes
    # the sentence does not need to run three commands to find it themselves.
    for insight in (insights or [])[:MAX_INSIGHTS]:
        line = f"likely: {insight.headline}"
        if insight.evidence:
            line += " (" + ", ".join(insight.evidence) + ")"
        table.notes.append(line)
        if insight.advice:
            table.notes.append(f"  -> {insight.advice}")

    # Then the command worth running next -- but only for the worst few. On a
    # badly broken machine every check fires, and fifteen suggestions is not a
    # next step, it is another wall of text.
    # Several checks can point at the same command -- memory and memory
    # pressure both send you to ps -- and the analysis above may already have
    # suggested it. Printing it three times does not make it three steps.
    already = {i.advice for i in (insights or [])}
    suggested: list[str] = []
    for result in shown:
        if result.status not in (BAD, WARN) or not result.follow_up:
            continue
        if result.follow_up in suggested or any(result.follow_up in a for a in already):
            continue
        suggested.append(result.follow_up)
    for command in suggested[:MAX_FOLLOW_UPS]:
        table.notes.append(f"next: {command}")
    if len(suggested) > MAX_FOLLOW_UPS:
        table.notes.append(f"...and {len(suggested) - MAX_FOLLOW_UPS} more to look at")
    return table


def explain(checks: list[Check] | None = None, area: str = "") -> str:
    """What every check looks at and where it draws the line.

    A number nobody can interpret is not a diagnosis, so the thresholds are
    part of the tool rather than buried in its source.
    """
    checks = CHECKS if checks is None else checks
    if area:
        checks = [c for c in checks if c.area == area.strip().lower()]
    lines: list[str] = []
    for name in AREAS:
        group = [c for c in checks if c.area == name]
        if not group:
            continue
        lines.append(f"{name.upper()}")
        for check in group:
            lines.append(f"  {check.title}")
            lines.append(f"    {check.about}")
            if check.follow_up:
                lines.append(f"    next: {check.follow_up}")
        lines.append("")
    return "\n".join(lines).rstrip()


def as_json(results: list[Result], insights: list[Insight] | None = None) -> str:
    """The whole diagnosis, for a monitoring agent rather than a person.

    The table export would carry only the three rendered columns; a machine
    reading this wants the areas, the analysis and the verdict too.
    """
    payload = {
        "verdict": verdict(results),
        "exit_code": exit_code(results),
        "counts": {
            status: sum(1 for r in results if r.status == status)
            for status in (BAD, WARN, OK, SKIP)
        },
        "checks": [
            {
                "key": r.key,
                "title": r.title,
                "area": r.area,
                "status": r.status,
                "detail": r.detail,
                "follow_up": r.follow_up,
            }
            for r in results
        ],
        "insights": [
            {
                "headline": i.headline,
                "severity": i.severity,
                "evidence": i.evidence,
                "advice": i.advice,
            }
            for i in (insights or [])
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def exit_code(results: list[Result]) -> int:
    """0 when clean, 1 when only warnings, 2 when something is critical."""
    if any(r.status == BAD for r in results):
        return 2
    if any(r.status == WARN for r in results):
        return 1
    return 0
