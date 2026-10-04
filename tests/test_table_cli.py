"""Tests for table mode reached through the command line."""

import io
import sys
from pathlib import Path

import pytest
from helpers import data_rows

from barem import cli

FIXTURES = Path(__file__).parent / "fixtures"
DF = (FIXTURES / "df-h.txt").read_text(encoding="utf-8")


def piped(monkeypatch, text: str):
    """Pretend standard input is a pipe carrying `text`."""

    class Pipe(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", Pipe(text))


def run(capsys, *argv):
    code = cli.main([*argv])
    out, err = capsys.readouterr()
    return code, out, err


# --- when table mode takes over ---------------------------------------------


def test_piped_input_is_formatted(monkeypatch, capsys):
    piped(monkeypatch, DF)
    code, out, _ = run(capsys, "--width", "80", "--no-color")
    assert code == 0
    assert "FILESYSTEM" in out
    assert "4 filesystems" in out


def test_a_command_name_still_means_examples(monkeypatch, capsys):
    """`df -h | barem find` looks up examples; it does not format."""
    piped(monkeypatch, DF)
    code, out, _ = run(capsys, "find", "size", "--no-color")
    assert code == 0
    assert out.startswith("find - ")
    assert "FILESYSTEM" not in out


def test_list_still_works_with_a_pipe(monkeypatch, capsys):
    piped(monkeypatch, DF)
    code, out, _ = run(capsys, "--list", "--no-color")
    assert code == 0
    assert "Available commands" in out


def test_search_still_works_with_a_pipe(monkeypatch, capsys):
    piped(monkeypatch, DF)
    code, out, _ = run(capsys, "-s", "port", "--no-color")
    assert code == 0
    assert "ss - " in out


def test_empty_pipe_prints_nothing(monkeypatch, capsys):
    piped(monkeypatch, "")
    code, out, _ = run(capsys, "--no-color")
    assert code == 0
    assert out.strip() == ""


def test_no_pipe_and_no_command_prints_help(monkeypatch, capsys):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty(""))
    code, out, _ = run(capsys, "--no-color")
    assert code == 0
    assert "usage:" in out


# --- the flags --------------------------------------------------------------


def test_sort_with_a_leading_dash(monkeypatch, capsys):
    """`--sort -size` must not be read as another option."""
    piped(monkeypatch, DF)
    code, out, _ = run(capsys, "--sort", "-size", "--width", "90", "--no-color")
    assert code == 0
    assert data_rows(out)[0].split()[0] == "/dev/sdb1"


def test_top_and_where(monkeypatch, capsys):
    piped(monkeypatch, DF)
    code, out, _ = run(capsys, "--where", "use% > 80", "--width", "90", "--no-color")
    assert code == 0
    assert "/data" in out and "/boot/efi" not in out


def test_format_json(monkeypatch, capsys):
    import json

    piped(monkeypatch, DF)
    code, out, _ = run(capsys, "--format", "json")
    assert code == 0
    assert len(json.loads(out)) == 4


def test_box_style(monkeypatch, capsys):
    piped(monkeypatch, DF)
    _, out, _ = run(capsys, "--box", "--width", "80", "--no-color")
    assert out.lstrip().startswith("┌")


def test_ascii_style(monkeypatch, capsys):
    piped(monkeypatch, DF)
    _, out, _ = run(capsys, "--ascii", "--width", "80", "--no-color")
    assert "─" not in out


def test_raw_passes_the_input_through(monkeypatch, capsys):
    piped(monkeypatch, DF)
    _, out, _ = run(capsys, "--raw")
    assert out.rstrip("\n") == DF.rstrip("\n")


def test_as_forces_a_profile(monkeypatch, capsys):
    piped(monkeypatch, DF)
    _, out, _ = run(capsys, "--as", "df", "--width", "90", "--no-color")
    assert "4 filesystems" in out


def test_width_env_var(monkeypatch, capsys):
    monkeypatch.setenv("BAREM_WIDTH", "60")
    piped(monkeypatch, DF)
    _, out, _ = run(capsys, "--no-color")
    from barem.table.width import display_width

    for line in out.splitlines():
        assert display_width(line) <= 60


def test_profiles_are_listed(capsys):
    code, out, _ = run(capsys, "--profiles", "--no-color")
    assert code == 0
    assert "df" in out and "docker ps" in out


def test_table_flags_do_not_need_a_pipe(monkeypatch, capsys):
    """An explicit table flag is intent enough, even without a tty check."""
    piped(monkeypatch, DF)
    code, out, _ = run(capsys, "--as", "df", "--no-color", "--width", "80")
    assert code == 0 and "FILESYSTEM" in out


# --- wrapper mode -----------------------------------------------------------


def test_split_command_keeps_the_commands_own_flags():
    from barem.table.runner import split_command

    assert split_command(["--width", "60", "df", "-h"]) == (["--width", "60"], ["df", "-h"])
    assert split_command(["df", "-i"]) == ([], ["df", "-i"])
    assert split_command(["--box", "ps", "aux"]) == (["--box"], ["ps", "aux"])


def test_split_command_honours_a_double_dash():
    from barem.table.runner import split_command

    assert split_command(["--", "df", "-h"]) == ([], ["df", "-h"])


def test_run_wrapper_formats_a_real_command(capsys):
    """Width 60 so it renders as a table; below 50 it would be cards."""
    script = "print('NAME   SIZE'); print('alpha  10G'); print('beta   20G')"
    code = cli.main(["run", "--no-color", "--width", "60", sys.executable, "-c", script])
    out, _ = capsys.readouterr()
    assert code == 0
    assert "NAME" in out and "SIZE" in out
    assert "alpha" in out and "beta" in out
    assert "2 rows" in out


def test_run_wrapper_reports_a_missing_command(capsys):
    code = cli.main(["run", "definitely-not-a-real-command-xyz"])
    _, err = capsys.readouterr()
    assert code != 0
    assert "not found" in err


@pytest.mark.parametrize("flag", ["--sort", "--cols", "--as"])
def test_dash_values_are_joined(flag):
    joined = cli.join_dash_values([flag, "-x", "rest"])
    assert joined == [f"{flag}=-x", "rest"]


def test_dash_values_leaves_normal_arguments_alone():
    assert cli.join_dash_values(["--width", "80"]) == ["--width", "80"]
