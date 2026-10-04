"""Tests for `barem help`, the first-try diagnostics.

Every check is fed real Linux command output rather than being run against
the machine the tests happen to be on, so the judgements are deterministic
and the suite passes on Windows and in CI alike.
"""

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
        assert check.argv or check.path, check.key
        assert check.follow_up, check.key


def test_check_keys_are_unique():
    keys = [c.key for c in diagnose.CHECKS]
    assert len(keys) == len(set(keys))


def test_checks_are_read_only():
    """Nothing here may change the machine it is diagnosing."""
    forbidden = {"rm", "kill", "systemctl", "mount", "umount", "dd", "mkfs", "reboot"}
    for check in diagnose.CHECKS:
        if not check.argv:
            continue
        if check.argv[0] == "systemctl":
            # read-only subcommands only
            assert check.argv[1] in ("--failed", "show", "list-units", "status"), check.argv
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
