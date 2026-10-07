"""Tests for `barem help`, the first-try diagnostics.

Every check is fed real Linux command output rather than being run against
the machine the tests happen to be on, so the judgements are deterministic
and the suite passes on Windows and in CI alike.
"""

import json

import pytest

from barem import diagnose
from barem.diagnose import BAD, MISSING, OK, SKIP, WARN, Check, Result

# --- realistic command output -----------------------------------------------

DF_OK = """Filesystem     1024-blocks      Used Available Capacity Mounted on
/dev/nvme0n1p2   490000000 117000000 348000000      26% /
/dev/nvme0n1p1      523248     63488    459760      13% /boot/efi
tmpfs             16384000      2148  16381852       1% /run
"""

DF_FULL = """Filesystem     1024-blocks       Used Available Capacity Mounted on
/dev/nvme0n1p2   490000000  117000000 348000000      26% /
/dev/sdb1       1920000000 1824000000  45000000      96% /data
"""

DF_HIGH = """Filesystem     1024-blocks      Used Available Capacity Mounted on
/dev/nvme0n1p2   490000000 400000000  90000000      82% /
"""

DF_INODES_FULL = """Filesystem      Inodes  IUsed  IFree IUse% Mounted on
/dev/nvme0n1p2 30539776 412233 30127543    2% /
/dev/sdb1        524288 523900     388   100% /data
"""

MEMINFO_OK = """MemTotal:       32740160 kB
MemFree:         2100000 kB
MemAvailable:   18900000 kB
SwapTotal:       8388604 kB
SwapFree:        6800000 kB
"""

MEMINFO_LOW = """MemTotal:       32740160 kB
MemFree:          120000 kB
MemAvailable:     900000 kB
SwapTotal:       8388604 kB
SwapFree:         400000 kB
"""

MOUNTS_OK = """/dev/nvme0n1p2 / ext4 rw,relatime 0 0
/dev/sdb1 /data xfs rw,relatime 0 0
tmpfs /run tmpfs rw,nosuid 0 0
"""

MOUNTS_READONLY = """/dev/nvme0n1p2 / ext4 rw,relatime 0 0
/dev/sdb1 /data ext4 ro,relatime 0 0
"""

FAILED_UNITS = """myapp-worker.service loaded failed failed MyApp background worker
nginx.service loaded failed failed A high performance web server
"""

OOM_LOG = """kernel: Out of memory: Killed process 4821 (firefox) total-vm:4891234kB
kernel: oom_reaper: reaped process 4821 (firefox)
"""

KERNEL_IO_ERROR = """kernel: EXT4-fs error (device sdb1): ext4_find_entry:1455: inode #2: comm ls: reading directory lblock 0
kernel: blk_update_request: I/O error, dev sdb, sector 1234567
"""


def judge(key: str, text: str) -> tuple[str, str]:
    """Run one named check's judge over the given text."""
    check = next(c for c in diagnose.CHECKS if c.key == key)
    return check.judge(text)


# --- disk ------------------------------------------------------------------


def test_disk_ok():
    status, detail = judge("disk", DF_OK)
    assert status == OK
    assert "26%" in detail


def test_disk_full_is_critical():
    status, detail = judge("disk", DF_FULL)
    assert status == BAD
    assert "/data 96%" in detail


def test_disk_high_is_a_warning():
    assert judge("disk", DF_HIGH)[0] == WARN


def test_pseudo_filesystems_are_ignored():
    """tmpfs at 100% is normal and must not raise an alarm."""
    text = """Filesystem 1024-blocks Used Available Capacity Mounted on
tmpfs 4096 4096 0 100% /run/user/1000
tmpfs 4096 4096 0 100% /dev/shm
/dev/nvme0n1p2 490000000 117000000 348000000 26% /
"""
    status, detail = judge("disk", text)
    assert status == OK, detail


def test_disk_percent_column_found_by_header_not_position():
    """`df -Pi` names it IUse%, not Capacity, and a fixed index misreads it."""
    status, detail = judge("inodes", DF_INODES_FULL)
    assert status == BAD
    assert "/data 100%" in detail


def test_inodes_ok():
    assert (
        judge(
            "inodes",
            """Filesystem Inodes IUsed IFree IUse% Mounted on
/dev/nvme0n1p2 30539776 412233 30127543 2% /
""",
        )[0]
        == OK
    )


def test_unreadable_df_is_skipped_not_guessed():
    assert judge("disk", "something that is not df output")[0] == SKIP


def test_mount_point_with_a_space_survives():
    text = """Filesystem 1024-blocks Used Available Capacity Mounted on
/dev/sdc1 100000 95000 5000 95% /mnt/my disk
"""
    status, detail = judge("disk", text)
    assert status == BAD
    assert "/mnt/my disk" in detail


# --- memory and load -------------------------------------------------------


def test_memory_ok():
    status, detail = judge("memory", MEMINFO_OK)
    assert status == OK
    assert "available" in detail


def test_memory_low_is_critical():
    assert judge("memory", MEMINFO_LOW)[0] == BAD


def test_swap_mostly_used_is_a_warning():
    assert judge("swap", MEMINFO_LOW)[0] == WARN


def test_no_swap_configured_is_fine():
    assert judge("swap", "MemTotal: 100 kB\nSwapTotal: 0 kB\n") == (OK, "no swap configured")


def test_load_compared_against_core_count(monkeypatch):
    monkeypatch.setattr(diagnose.os, "cpu_count", lambda: 4)
    assert judge("load", "0.50 0.40 0.30 1/500 1234")[0] == OK
    assert judge("load", "5.00 4.00 3.00 1/500 1234")[0] == WARN
    assert judge("load", "9.00 8.00 7.00 1/500 1234")[0] == BAD


# --- services and the kernel ----------------------------------------------


def test_no_failed_units():
    assert judge("units", "") == (OK, "none")


def test_failed_units_are_named():
    status, detail = judge("units", FAILED_UNITS)
    assert status == BAD
    assert "myapp-worker.service" in detail


def test_read_only_filesystem_is_critical():
    """The classic silent outage: the disk is there but nothing can write."""
    status, detail = judge("readonly", MOUNTS_READONLY)
    assert status == BAD
    assert "/data" in detail


def test_writable_filesystems_are_fine():
    assert judge("readonly", MOUNTS_OK)[0] == OK


def test_oom_kill_names_the_victim():
    status, detail = judge("oom", OOM_LOG)
    assert status == BAD
    assert "firefox" in detail


def test_no_oom_is_fine():
    assert judge("oom", "kernel: nothing of note\n")[0] == OK


def test_io_error_is_critical():
    assert judge("kernel", KERNEL_IO_ERROR)[0] == BAD


def test_other_kernel_errors_are_a_warning():
    assert judge("kernel", "kernel: some unrelated error\n")[0] == WARN


def test_no_kernel_errors():
    assert judge("kernel", "")[0] == OK


# --- network and clock -----------------------------------------------------


def test_default_route_present():
    assert judge("route", "default via 192.168.1.1 dev eth0 proto dhcp metric 100")[0] == OK


def test_no_default_route_is_critical():
    assert judge("route", "")[0] == BAD


def test_dns_answers():
    assert judge("dns", "127.0.0.1       localhost")[0] == OK


def test_dns_silent_is_critical():
    assert judge("dns", "")[0] == BAD


def test_clock_synchronised():
    assert judge("clock", "NTPSynchronized=yes")[0] == OK


def test_clock_not_synchronised_is_a_warning():
    """A wrong clock breaks TLS and tokens, and is easy to overlook."""
    assert judge("clock", "NTPSynchronized=no")[0] == WARN


# --- file-based checks -----------------------------------------------------


def test_reboot_not_required_when_the_file_is_absent():
    assert judge("reboot", MISSING) == (OK, "not required")


def test_reboot_pending_when_the_file_exists():
    assert judge("reboot", "*** System restart required ***\n")[0] == WARN


def test_reboot_pending_when_the_file_is_present_but_empty():
    """An absent file and an empty one mean different things."""
    assert judge("reboot", "")[0] == WARN


def test_file_descriptors():
    assert judge("fds", "1536\t0\t9223372036854775807\n")[0] == OK
    assert judge("fds", "900000\t0\t1000000\n")[0] == BAD
    assert judge("fds", "700000\t0\t1000000\n")[0] == WARN


def test_zombies():
    assert judge("zombies", "STAT\nSs\nRl\nSl\n")[0] == OK
    assert judge("zombies", "STAT\n" + "Z\n" * 20)[0] == WARN


# --- the runner ------------------------------------------------------------


def test_a_missing_command_is_skipped_not_failed():
    check = Check("x", "x", argv=["definitely-not-a-command-xyz"], judge=lambda t: (OK, ""))
    results = diagnose.run_checks([check])
    assert results[0].status == SKIP
    assert "unavailable" in results[0].detail


def test_a_broken_judge_does_not_break_the_report():
    def explode(_text):
        raise ValueError("boom")

    check = Check("x", "x", path="/whatever", judge=explode)
    results = diagnose.run_checks([check], collect=lambda _c: "data")
    assert results[0].status == SKIP
    assert "ValueError" in results[0].detail


def test_every_check_has_a_judge_and_a_follow_up():
    for check in diagnose.CHECKS:
        assert check.key and check.title
        assert check.argv or check.path or check.paths or check.glob, check.key
        assert check.follow_up, check.key


def test_checks_are_read_only():
    """Nothing here may change the machine it is diagnosing."""
    forbidden = {"rm", "kill", "systemctl", "mount", "umount", "dd", "mkfs", "reboot"}
    for check in diagnose.CHECKS:
        if not check.argv:
            continue
        if check.argv[0] == "systemctl":
            # read-only subcommands only
            assert check.argv[1] in (
                "--failed",
                "show",
                "list-units",
                "status",
                "is-system-running",
            ), check.argv
            continue
        assert check.argv[0] not in forbidden, check.argv


# --- reporting -------------------------------------------------------------


def results_for(*statuses) -> list[Result]:
    return [Result(f"k{i}", f"check {i}", s, "detail") for i, s in enumerate(statuses)]


def test_only_problems_are_shown_by_default():
    table = diagnose.build_table(results_for(OK, OK, BAD, WARN))
    assert len(table.rows) == 2
    assert {r["status"] for r in table.rows} == {BAD, WARN}


def test_all_shows_everything():
    table = diagnose.build_table(results_for(OK, OK, BAD, WARN), show_all=True)
    assert len(table.rows) == 4


def test_worst_first():
    table = diagnose.build_table(results_for(OK, SKIP, WARN, BAD), show_all=True)
    assert [r["status"] for r in table.rows] == [BAD, WARN, OK, SKIP]


def test_summary_counts_everything_not_just_what_is_shown():
    table = diagnose.build_table(results_for(OK, OK, OK, BAD))
    assert "1 critical" in table.summary
    assert "3 passed" in table.summary


def test_summary_says_so_when_nothing_is_wrong():
    table = diagnose.build_table(results_for(OK, OK))
    assert "nothing wrong found" in table.summary
    assert table.rows == []


def test_follow_up_commands_are_offered_for_problems():
    results = [Result("disk", "disk space", BAD, "full", "df -h | barem")]
    table = diagnose.build_table(results)
    assert any("df -h | barem" in note for note in table.notes)


def test_no_follow_up_for_passing_checks():
    results = [Result("disk", "disk space", OK, "fine", "df -h | barem")]
    table = diagnose.build_table(results, show_all=True)
    assert not table.notes


@pytest.mark.parametrize(
    ("statuses", "code"),
    [
        ((OK, OK), 0),
        ((OK, SKIP), 0),
        ((OK, WARN), 1),
        ((WARN, WARN), 1),
        ((OK, BAD), 2),
        ((WARN, BAD), 2),
    ],
)
def test_exit_code(statuses, code):
    """0 clean, 1 warnings only, 2 something critical -- usable in a script."""
    assert diagnose.exit_code(results_for(*statuses)) == code


# --- pressure, saturation and contention ------------------------------------

PSI_QUIET = """some avg10=0.00 avg60=0.00 avg300=0.00 total=0
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
"""

PSI_RISING = """some avg10=62.00 avg60=35.00 avg300=4.00 total=8812345
full avg10=40.00 avg60=20.00 avg300=2.00 total=4412345
"""

PSI_EASING = """some avg10=2.00 avg60=12.00 avg300=48.00 total=8812345
full avg10=1.00 avg60=6.00 avg300=20.00 total=4412345
"""

STAT_QUIET = """cpu  120000 500 40000 9000000 8000 0 900 0 0 0
cpu0 60000 250 20000 4500000 4000 0 450 0 0 0
intr 123456
"""

STAT_STOLEN = """cpu  120000 500 40000 600000 8000 0 900 90000 0 0
intr 123456
"""

STAT_IOWAIT = """cpu  120000 500 40000 400000 200000 0 900 0 0 0
intr 123456
"""


def test_pressure_quiet_is_ok():
    status, detail = judge("psi_io", PSI_QUIET)
    assert status == OK
    assert "0%" in detail


def test_pressure_reports_the_trend():
    """Whether it is getting worse is the thing you actually want to know."""
    status, detail = judge("psi_io", PSI_RISING)
    assert status == BAD
    assert "rising" in detail

    status, detail = judge("psi_cpu", PSI_EASING)
    assert "easing" in detail


def test_pressure_thresholds_differ_by_resource():
    """12% of a minute blocked on disk is serious; on cpu it is nothing."""
    moderate = "some avg10=12.00 avg60=12.00 avg300=12.00 total=1\n"
    assert judge("psi_io", moderate)[0] == WARN
    assert judge("psi_cpu", moderate)[0] == OK


def test_pressure_without_psi_is_skipped():
    assert judge("psi_cpu", "")[0] == SKIP


def test_steal_time_names_the_hypervisor():
    status, detail = judge("steal", STAT_STOLEN)
    assert status == BAD
    assert "hypervisor" in detail


def test_steal_time_quiet():
    assert judge("steal", STAT_QUIET)[0] == OK


def test_iowait_is_judged_separately_from_steal():
    assert judge("iowait", STAT_IOWAIT)[0] == BAD
    assert judge("steal", STAT_IOWAIT)[0] == OK


def test_cpu_times_without_a_cpu_line():
    assert judge("iowait", "intr 1 2 3")[0] == SKIP


MEMINFO_DIRTY = """MemTotal:       32740160 kB
MemAvailable:   18900000 kB
Dirty:           2100000 kB
Writeback:       1800000 kB
"""

MEMINFO_CLEAN = """MemTotal:       32740160 kB
MemAvailable:   18900000 kB
Dirty:              1024 kB
Writeback:             0 kB
"""


def test_writeback_in_flight_warns():
    status, detail = judge("dirty", MEMINFO_DIRTY)
    assert status == WARN
    assert "in flight" in detail


def test_dirty_pages_normally_fine():
    assert judge("dirty", MEMINFO_CLEAN)[0] == OK


PS_DSTATE = """STAT COMMAND
Ss   systemd
D    kworker/u8:3
D    rsync
Dl   nfsd
D    rsync
D    tar
"""

PS_NO_DSTATE = """STAT COMMAND
Ss   systemd
S    nginx
"""


def test_uninterruptible_processes_are_critical_in_numbers():
    status, detail = judge("dstate", PS_DSTATE)
    assert status == BAD
    assert "5 stuck" in detail
    # Repeats collapse: three rsyncs is one cause, not three.
    assert detail.count("rsync") == 1


def test_no_stuck_processes():
    assert judge("dstate", PS_NO_DSTATE) == (OK, "none")


# --- network ----------------------------------------------------------------


def test_conntrack_full_is_critical():
    status, detail = judge("conntrack", "259000\n262144\n")
    assert status == BAD
    assert "99%" in detail


def test_conntrack_quiet():
    assert judge("conntrack", "1200\n262144\n")[0] == OK


def test_conntrack_needs_both_numbers():
    assert judge("conntrack", "1200\n")[0] == SKIP


NET_DEV_CLEAN = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1000000   10000    0    0    0     0          0         0  1000000   10000    0    0    0     0       0          0
  eth0: 980000000 8000000    0    2    0     0          0         0 410000000 4000000    0    0    0     0       0          0
"""

NET_DEV_DROPPING = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
  eth0: 980000000 1000000  500 25000    0     0          0         0 410000000 400000    0    0    0     0       0          0
"""


def test_interface_drops_are_judged_as_a_rate():
    """A raw counter means nothing on a machine that has been up a year."""
    status, detail = judge("netdev", NET_DEV_DROPPING)
    assert status == BAD
    assert "eth0" in detail


def test_clean_interface():
    assert judge("netdev", NET_DEV_CLEAN)[0] == OK


def test_loopback_is_not_judged():
    assert "lo" not in judge("netdev", NET_DEV_CLEAN)[1]


NETSTAT_OK = """TcpExt: SyncookiesSent ListenOverflows ListenDrops TCPSynRetrans
TcpExt: 0 0 0 12
IpExt: InOctets OutOctets
IpExt: 100 200
"""

NETSTAT_OVERFLOW = """TcpExt: SyncookiesSent ListenOverflows ListenDrops TCPSynRetrans
TcpExt: 0 4821 4821 900
"""


def test_listen_overflow_is_critical():
    status, detail = judge("tcp", NETSTAT_OVERFLOW)
    assert status == BAD
    assert "accept queue" in detail


def test_tcp_counters_clean():
    assert judge("tcp", NETSTAT_OK)[0] == OK


SOCKSTAT_OK = "sockets: used 400\nTCP: inuse 30 orphan 0 tw 120 alloc 40 mem 3\n"
SOCKSTAT_TIMEWAIT = "sockets: used 40000\nTCP: inuse 300 orphan 4 tw 24000 alloc 400 mem 30\n"


def test_time_wait_pile_warns_about_ports():
    status, detail = judge("sockets", SOCKSTAT_TIMEWAIT)
    assert status == WARN
    assert "ephemeral" in detail


def test_sockets_quiet():
    assert judge("sockets", SOCKSTAT_OK)[0] == OK


def test_hostname_resolves():
    assert judge("hostname", "web-01.example.com\n")[0] == OK


@pytest.mark.parametrize(
    "answer",
    ["", "hostname: Name or service not known", "hostname: Temporary failure in name resolution"],
)
def test_hostname_that_does_not_resolve_warns(answer):
    """`hostname -f` writes this to stderr and can still exit zero."""
    status, detail = judge("hostname", answer)
    assert status == WARN
    assert "sudo" in detail


SS_SAFE = """LISTEN 0 128 127.0.0.1:5432 0.0.0.0:*
LISTEN 0 511 0.0.0.0:80   0.0.0.0:*
LISTEN 0 128 0.0.0.0:22   0.0.0.0:*
"""

SS_EXPOSED = """LISTEN 0 128 0.0.0.0:5432 0.0.0.0:*
LISTEN 0 511 0.0.0.0:80   0.0.0.0:*
LISTEN 0 128 [::]:6379    [::]:*
"""


def test_a_database_on_every_interface_is_reported():
    status, detail = judge("exposed", SS_EXPOSED)
    assert status == WARN
    assert "postgres" in detail and "redis" in detail


def test_a_web_server_on_every_interface_is_not():
    """Port 80 is meant to answer the world; 5432 is not."""
    assert judge("exposed", SS_SAFE)[0] == OK


# --- system state -----------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("running\n", OK),
        ("degraded\n", BAD),
        ("maintenance\n", BAD),
        ("starting\n", WARN),
        ("", SKIP),
    ],
)
def test_system_state(answer, expected):
    assert judge("state", answer)[0] == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [("90.5 180.0", "up 1m"), ("7200.0 1.0", "up 2h 0m"), ("200000.0 1.0", "up 2d 7h")],
)
def test_uptime_is_readable(seconds, expected):
    status, detail = judge("uptime", seconds)
    assert status == OK
    assert detail == expected


BOOT_SAME = "/boot/vmlinuz-6.8.0-45-generic: \n"
BOOT_NEWER = "/boot/vmlinuz-6.8.0-45-generic: \n/boot/vmlinuz-6.8.0-100-generic: \n"


def test_a_newer_installed_kernel_means_a_reboot(monkeypatch):
    monkeypatch.setattr(diagnose.platform, "release", lambda: "6.8.0-45-generic")
    status, detail = judge("kernel_version", BOOT_NEWER)
    assert status == WARN
    assert "6.8.0-100-generic" in detail


def test_running_the_newest_kernel(monkeypatch):
    monkeypatch.setattr(diagnose.platform, "release", lambda: "6.8.0-45-generic")
    assert judge("kernel_version", BOOT_SAME)[0] == OK


def test_kernel_versions_sort_numerically(monkeypatch):
    """6.8.0-100 is newer than 6.8.0-99, which string order gets backwards."""
    monkeypatch.setattr(diagnose.platform, "release", lambda: "6.8.0-100-generic")
    text = "/boot/vmlinuz-6.8.0-99-generic: \n/boot/vmlinuz-6.8.0-100-generic: \n"
    assert judge("kernel_version", text)[0] == OK


COREDUMPS = """TIME                         PID  UID  GID SIG     COREFILE EXE
Mon 2026-09-28 11:02:03 UTC 4821 1000 1000 SIGSEGV present  /usr/bin/myapp
Tue 2026-09-29 04:40:11 UTC 5120 1000 1000 SIGABRT present  /usr/bin/myapp
"""


def test_recent_crashes_are_named():
    status, detail = judge("crashes", COREDUMPS)
    assert status == WARN
    assert "myapp" in detail and "2 crash" in detail


def test_no_crashes():
    assert judge("crashes", "")[0] == OK


def test_journal_size_is_reported():
    text = "Archived and active journals take up 3.9G in the file system.\n"
    status, detail = judge("journal", text)
    assert status == OK
    assert "3.9G" in detail


def test_an_oversized_journal_suggests_vacuuming():
    text = "Archived and active journals take up 24.0G in the file system.\n"
    status, detail = judge("journal", text)
    assert status == WARN
    assert "vacuum" in detail


def test_security_updates_warn():
    text = "17 updates can be applied immediately.\n3 of these updates are security updates.\n"
    status, detail = judge("updates", text)
    assert status == WARN
    assert "3 of them security" in detail


def test_ordinary_updates_do_not_warn():
    text = "5 updates can be applied immediately.\n"
    assert judge("updates", text)[0] == OK


AUTH_QUIET = "Sep 28 11:00:00 web-01 sshd[1]: Accepted publickey for merab from 10.0.0.5\n"
AUTH_BRUTE = "".join(
    f"Sep 28 11:0{i % 10}:00 web-01 sshd[{i}]: Failed password for invalid user admin from 1.2.3.4\n"
    for i in range(60)
)


def test_a_brute_force_is_called_what_it_is():
    status, detail = judge("auth", AUTH_BRUTE)
    assert status == WARN
    assert "brute force" in detail


def test_a_successful_login_is_not_a_failure():
    assert judge("auth", AUTH_QUIET)[0] == OK


# --- the analysis -----------------------------------------------------------


def _results(**statuses) -> list[Result]:
    """Build a result set where the named checks have the given status.

    Everything else passes, so a pattern can only fire on what is named.
    """
    out = []
    for check in diagnose.CHECKS:
        status = statuses.get(check.key, OK)
        out.append(Result(check.key, check.title, status, "", check.follow_up, area=check.area))
    return out


def test_memory_exhaustion_is_named_from_several_checks():
    insights = diagnose.analyse(_results(memory=BAD, oom=BAD, psi_memory=WARN))
    assert insights
    assert "running out of memory" in insights[0].headline
    assert "oom" in insights[0].evidence
    assert insights[0].severity == BAD


def test_a_single_failing_check_is_not_a_pattern():
    """One red row is a fact, not a diagnosis. Say nothing rather than guess."""
    assert diagnose.analyse(_results(journal=WARN)) == []


def test_steal_time_excuses_the_load():
    """High load plus steal is the host's fault; the cpu pattern must not fire."""
    insights = diagnose.analyse(_results(steal=BAD, load=BAD, psi_cpu=BAD))
    headlines = [i.headline for i in insights]
    assert any("hypervisor" in h for h in headlines)
    assert not any("genuinely busy" in h for h in headlines)


def test_load_without_steal_is_the_machine_being_busy():
    insights = diagnose.analyse(_results(load=WARN, psi_cpu=WARN))
    assert any("genuinely busy" in i.headline for i in insights)


def test_inodes_without_disk_space_is_called_out():
    """The confusing one: df shows room, writes fail anyway."""
    insights = diagnose.analyse(_results(inodes=BAD))
    assert any("inodes are gone" in i.headline for i in insights)


def test_inodes_with_a_full_disk_is_just_a_full_disk():
    insights = diagnose.analyse(_results(inodes=BAD, disk=BAD))
    assert not any("inodes are gone" in i.headline for i in insights)


def test_insights_are_worst_first():
    insights = diagnose.analyse(_results(memory=BAD, oom=BAD, kernel_version=WARN, reboot=WARN))
    assert [i.severity for i in insights] == sorted(
        (i.severity for i in insights), key=lambda s: diagnose.RANK[s]
    )


def test_a_healthy_machine_has_nothing_to_say():
    assert diagnose.analyse(_results()) == []


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [({}, "healthy"), ({"journal": WARN}, "degraded"), ({"disk": BAD}, "critical")],
)
def test_verdict(statuses, expected):
    assert diagnose.verdict(_results(**statuses)) == expected


# --- areas, explaining and the json report ----------------------------------


def test_every_check_has_a_known_area_and_a_description():
    for check in diagnose.CHECKS:
        assert check.area in diagnose.AREAS, check.key
        assert check.about, check.key


def test_check_keys_are_unique():
    keys = [c.key for c in diagnose.CHECKS]
    assert len(keys) == len(set(keys))


def test_every_pattern_names_real_checks():
    """A pattern pointing at a check that does not exist can never fire."""
    keys = {c.key for c in diagnose.CHECKS}
    for pattern in diagnose.PATTERNS:
        for key in pattern.needs + pattern.any_of + pattern.unless:
            assert key in keys, f"{pattern.name} -> {key}"


def test_select_narrows_to_one_area():
    results = _results()
    memory = diagnose.select(results, "memory")
    assert memory
    assert {r.area for r in memory} == {"memory"}
    assert len(memory) < len(results)


def test_select_without_an_area_keeps_everything():
    results = _results()
    assert diagnose.select(results, "") == results


def test_explain_describes_every_check():
    text = diagnose.explain()
    for check in diagnose.CHECKS:
        assert check.title in text
    for area in diagnose.AREAS:
        assert area.upper() in text


def test_explain_can_be_narrowed():
    text = diagnose.explain(area="memory")
    assert "MEMORY" in text
    assert "NETWORK" not in text


def test_json_report_carries_the_analysis():
    results = _results(memory=BAD, oom=BAD)
    payload = json.loads(diagnose.as_json(results, diagnose.analyse(results)))
    assert payload["verdict"] == "critical"
    assert payload["exit_code"] == 2
    assert payload["counts"]["bad"] == 2
    assert payload["insights"]
    assert payload["insights"][0]["evidence"]
    assert {c["key"] for c in payload["checks"]} == {c.key for c in diagnose.CHECKS}


def test_the_table_carries_the_insights():
    results = _results(memory=BAD, oom=BAD)
    table = diagnose.build_table(results, insights=diagnose.analyse(results))
    assert any(note.startswith("likely:") for note in table.notes)
    assert any("->" in note for note in table.notes)


def test_the_table_stays_short_when_everything_is_broken():
    """Fifteen suggestions is not a next step, it is another wall of text."""
    results = _results(**{c.key: BAD for c in diagnose.CHECKS})
    table = diagnose.build_table(results, insights=diagnose.analyse(results))
    assert sum(1 for n in table.notes if n.startswith("next:")) <= diagnose.MAX_FOLLOW_UPS
    assert sum(1 for n in table.notes if n.startswith("likely:")) <= diagnose.MAX_INSIGHTS


# --- the new data sources ---------------------------------------------------


def test_several_files_are_read_in_order(tmp_path):
    count = tmp_path / "count"
    maximum = tmp_path / "max"
    count.write_text("1200\n", encoding="utf-8")
    maximum.write_text("262144\n", encoding="utf-8")
    check = Check("c", "c", paths=[str(count), str(maximum)])
    assert diagnose.gather(check).split() == ["1200", "262144"]


def test_a_missing_half_makes_the_check_unavailable(tmp_path):
    """A count without its maximum says nothing, so it is skipped, not judged."""
    count = tmp_path / "count"
    count.write_text("1200\n", encoding="utf-8")
    check = Check("c", "c", paths=[str(count), str(tmp_path / "absent")])
    assert diagnose.gather(check) is None


def test_a_glob_reports_which_file_each_value_came_from(tmp_path):
    (tmp_path / "vmlinuz-6.8.0-45").write_text("", encoding="utf-8")
    (tmp_path / "vmlinuz-6.8.0-100").write_text("", encoding="utf-8")
    check = Check("c", "c", glob=str(tmp_path / "vmlinuz-*"))
    text = diagnose.gather(check)
    assert "vmlinuz-6.8.0-45" in text and "vmlinuz-6.8.0-100" in text


def test_a_glob_that_matches_nothing_is_unavailable(tmp_path):
    assert diagnose.gather(Check("c", "c", glob=str(tmp_path / "nothing-*"))) is None


def test_the_same_command_is_not_suggested_twice():
    """Memory and memory pressure both point at ps; once is enough."""
    results = _results(memory=BAD, psi_memory=BAD)
    table = diagnose.build_table(results, insights=diagnose.analyse(results))
    nexts = [n for n in table.notes if n.startswith("next:")]
    assert len(nexts) == len(set(nexts))


def test_a_command_the_analysis_already_gave_is_not_repeated():
    results = _results(memory=BAD, oom=BAD)
    insights = diagnose.analyse(results)
    table = diagnose.build_table(results, insights=insights)
    advice = [i.advice for i in insights]
    for note in (n for n in table.notes if n.startswith("next:")):
        assert not any(note[len("next: ") :] in a for a in advice)
