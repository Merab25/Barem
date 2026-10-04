"""Tests for the parsers and for kind inference.

Section 8.2 of the design lists the ways `line.split()` fails on real command
output. Each of those failures gets a test here.
"""

import pytest

from gamaxsene.table.detect import build_table, detect_format, parse_input
from gamaxsene.table.humanize import (
    human_duration,
    human_size,
    parse_duration,
    parse_percent,
    parse_size,
    sort_value,
)
from gamaxsene.table.model import Kind
from gamaxsene.table.parse import columnar
from gamaxsene.table.theme import status_group

DF = """Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1p2  468G  112G  332G  25% /
/dev/sdb1       1.8T  1.7T   43G  95% /data
tmpfs            16G  2.1M   16G   1% /run
"""

PS = """USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root           1  0.0  0.1 168404 11952 ?        Ss   09:14   0:03 /sbin/init splash
merab       4821 94.3 12.5 489123 20480 ?        Rl   10:02  12:44 /usr/lib/firefox/firefox -contentproc
"""

DOCKER = """CONTAINER ID   IMAGE          COMMAND                  CREATED        STATUS                      PORTS                  NAMES
a1b2c3d4e5f6   nginx:alpine   "/docker-entrypoint."    2 hours ago    Up 2 hours                  0.0.0.0:8080->80/tcp   web
9a8b7c6d5e4f   redis:7        "docker-entrypoint.s"    3 days ago     Exited (137) 5 hours ago                           cache
"""


# --- the failures that defeat split() ---------------------------------------


def test_header_containing_a_space_stays_one_column():
    """df's "Mounted on" is one column, not two."""
    headers, rows = columnar.parse(DF)
    assert headers[-1].lower() == "mounted on"
    assert len(headers) == 6
    assert [r[-1] for r in rows] == ["/", "/data", "/run"]


def test_single_space_between_headers_still_separates_columns():
    """df separates "Used" and "Avail" by one space; they are two columns."""
    headers, _ = columnar.parse(DF)
    assert [h.lower() for h in headers[2:4]] == ["used", "avail"]


def test_right_aligned_header_is_read_whole():
    """A numeric header sits left of where its data starts."""
    headers, _ = columnar.parse(DF)
    assert [h.lower() for h in headers] == [
        "filesystem",
        "size",
        "used",
        "avail",
        "use%",
        "mounted on",
    ]


def test_command_column_keeps_its_spaces():
    """ps aux holds a whole command line in its last column."""
    headers, rows = columnar.parse(PS)
    assert len(headers) == 11
    assert rows[0][-1] == "/sbin/init splash"
    assert rows[1][-1] == "/usr/lib/firefox/firefox -contentproc"


def test_two_word_header_over_solid_data_is_one_column():
    """ "CONTAINER ID" is one column because the id runs through the gap."""
    headers, rows = columnar.parse(DOCKER)
    assert headers[0].lower() == "container id"
    assert rows[0][0] == "a1b2c3d4e5f6"


def test_status_phrase_with_spaces_is_not_split():
    """ "Exited (137) 5 hours ago" must survive, and not steal the next column."""
    headers, rows = columnar.parse(DOCKER)
    assert len(headers) == 7
    assert rows[1][4] == "Exited (137) 5 hours ago"
    assert rows[1][-1] == "cache"


def test_an_empty_value_does_not_shift_the_row():
    """The exited container has no ports; NAMES must still line up."""
    _, rows = columnar.parse(DOCKER)
    assert rows[0][5] == "0.0.0.0:8080->80/tcp"
    assert rows[1][5] == ""
    assert rows[1][6] == "cache"


def test_header_with_no_rows():
    headers, rows = columnar.parse("NAME   SIZE\n")
    assert rows == []
    assert headers


def test_empty_input():
    assert columnar.parse("") == ([], [])


def test_ragged_lines_do_not_raise():
    text = "A    B     C\n1    2     3\n4\n5    6\n"
    headers, rows = columnar.parse(text)
    assert len(headers) == 3
    assert all(len(r) == 3 for r in rows)


# --- profiles and inference -------------------------------------------------


def test_df_is_recognised_by_its_header():
    table = build_table(DF)
    assert table.name == "df"
    assert table.column("use_pct").kind is Kind.PERCENT
    assert table.column("filesystem").identity


def test_ps_is_recognised():
    assert build_table(PS).name == "ps aux"


def test_docker_is_recognised():
    table = build_table(DOCKER)
    assert table.name == "docker ps"
    assert table.column("status").kind is Kind.STATUS


def test_forcing_a_profile():
    assert build_table(DF, profile_name="df").name == "df"


def test_unknown_command_still_gets_sensible_kinds():
    """The generic path runs for every command without a profile."""
    text = "WIDGET   COUNT   SHARE   PATH\nalpha    1200    12.5%   /srv/alpha\nbeta     34      87.5%   /srv/beta\n"
    table = build_table(text)
    assert table.name is None
    kinds = {c.key: c.kind for c in table.columns}
    assert kinds["count"] is Kind.NUMBER
    assert kinds["share"] is Kind.PERCENT
    assert kinds["path"] is Kind.PATH


def test_nothing_is_lost_in_parsing():
    """Every value in the input appears in the table."""
    table = build_table(DF)
    flat = " ".join(" ".join(r.values()) for r in table.rows)
    for token in ("/dev/sdb1", "1.8T", "1.7T", "43G", "95%", "/data", "tmpfs"):
        assert token in flat


def test_no_cell_keeps_a_separator():
    table = build_table(DF)
    for row in table.rows:
        for value in row.values():
            assert value == value.strip()


# --- input formats ----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('[{"a": 1}]', "json"),
        ('{"a": 1}', "json"),
        ('{"a":1}\n{"a":2}\n', "jsonl"),
        ("a,b,c\n1,2,3\n", "csv"),
        ("a\tb\n1\t2\n", "tsv"),
        ('NAME="Ubuntu"\nVERSION_ID="24.04"\n', "keyvalue"),
        (DF, "columnar"),
    ],
)
def test_format_detection(text, expected):
    assert detect_format(text) == expected


def test_json_array_becomes_a_table():
    headers, rows, fmt = parse_input('[{"name":"web","port":80},{"name":"db","port":5432}]')
    assert fmt == "json"
    assert headers == ["name", "port"]
    assert rows == [["web", "80"], ["db", "5432"]]


def test_json_objects_with_different_keys_keep_every_column():
    headers, rows, _ = parse_input('[{"a":1},{"b":2}]')
    assert headers == ["a", "b"]
    assert rows == [["1", ""], ["", "2"]]


def test_keyvalue_input():
    headers, rows, _ = parse_input('NAME="Ubuntu"\nVERSION_ID="24.04"\n')
    assert headers == ["KEY", "VALUE"]
    assert rows == [["NAME", "Ubuntu"], ["VERSION_ID", "24.04"]]


def test_broken_json_falls_back_rather_than_raising():
    _headers, _rows, fmt = parse_input('[{"a": 1}, {oops', input_format="json")
    assert fmt == "columnar"


# --- humanizing and sorting -------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1.8T", 1.8 * 1024**4), ("512M", 512 * 1024**2), ("16G", 16 * 1024**3), ("100", 100.0)],
)
def test_parse_size(text, expected):
    assert parse_size(text) == pytest.approx(expected)


def test_size_round_trip():
    assert human_size(parse_size("1.8T")) == "1.8T"
    assert human_size(parse_size("512M")) == "512M"


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("3d4h", 3 * 86400 + 4 * 3600), ("22m", 1320), ("12:44", 764), ("1-02:03:04", 93784)],
)
def test_parse_duration(text, seconds):
    assert parse_duration(text) == pytest.approx(seconds)


def test_human_duration_keeps_two_units():
    assert human_duration(3 * 86400 + 4 * 3600) == "3d 4h"
    assert human_duration(1320) == "22m"


def test_percent_parsing():
    assert parse_percent("95%") == 95
    assert parse_percent("94.3") == pytest.approx(94.3)
    assert parse_percent("n/a") is None


def test_sorting_uses_real_values_not_text():
    """1.8T must sort above 512M, which string comparison gets wrong."""
    values = ["512M", "1.8T", "16G", "2.1M"]
    ordered = sorted(values, key=lambda v: sort_value(v, "size"))
    assert ordered == ["2.1M", "512M", "16G", "1.8T"]


def test_sorting_puts_empties_last():
    values = ["5", "", "-", "10"]
    ordered = sorted(values, key=lambda v: sort_value(v, "number"))
    assert ordered[:2] == ["5", "10"]


def test_sorting_mixed_values_does_not_raise():
    values = ["5", "abc", "", "1.8T"]
    assert len(sorted(values, key=lambda v: sort_value(v, "size"))) == 4


# --- status words -----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "group"),
    [
        ("Up 2 hours", "good"),
        ("Running", "good"),
        ("LISTEN", "good"),
        ("Completed", "good"),
        ("Pending", "busy"),
        ("ContainerCreating", "busy"),
        ("Exited (137) 5 hours ago", "bad"),
        ("CrashLoopBackOff", "bad"),
        ("inactive", "bad"),
        ("something-else", "neutral"),
        ("", "neutral"),
    ],
)
def test_status_grouping(value, group):
    assert status_group(value) == group
