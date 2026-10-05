"""Tests for barem. Run with: pytest"""

import shutil
import subprocess

import pytest

from barem import cli

NAMES = cli.available()


def run(capsys, *argv):
    """Run the CLI like a user would, return (exit code, stdout, stderr)."""
    code = cli.main([*argv, "--no-color"])
    out, err = capsys.readouterr()
    return code, out, err


# --- parser -----------------------------------------------------------------


def test_parse_file_format():
    text = (
        "## demo tool\n"
        "\n"
        "# first example\n"
        "demo --a\n"
        "\n"
        "# second example\n"
        "# continues here\n"
        "demo --b\n"
        "demo --c\n"
    )
    sheet = cli.parse("demo", text)
    assert sheet.title == "demo tool"
    assert [e.description for e in sheet.examples] == [
        "first example",
        "second example continues here",
    ]
    assert sheet.examples[1].commands == ["demo --b", "demo --c"]


def test_keyword_matching_is_case_insensitive_and_needs_all_words():
    example = cli.Example("Extract a gzip archive", ["tar -xzf archive.tar.gz"])
    assert example.matches(["EXTRACT", "gz"])
    assert not example.matches(["extract", "zip-not-here"])


def test_keyword_must_match_start_of_a_word():
    example = cli.Example("Use a profile", ["export AWS_PROFILE=work"])
    assert not example.matches(["port"])
    assert example.matches(["exp"])
    assert cli.Example("Open ports", ["ss -tln"]).matches(["port"])


# --- example files ------------------------------------------------------------


def test_many_commands_are_bundled():
    assert len(NAMES) >= 30


@pytest.mark.parametrize("name", NAMES)
def test_example_file_is_well_formed(name):
    sheet = cli.load(name)
    assert sheet.title, f"{name}.txt needs a '## summary' line at the top"
    assert len(sheet.examples) >= 20, f"{name}.txt has only {len(sheet.examples)} examples"
    assert all(example.description for example in sheet.examples)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
@pytest.mark.parametrize("name", NAMES)
def test_examples_are_valid_shell_syntax(name):
    """bash -n parses the commands without running them, catching typos like unclosed quotes."""
    script = "\n".join(cmd for example in cli.load(name).examples for cmd in example.commands)
    # Send bytes, not text: on Windows text mode rewrites newlines as CRLF and bash then
    # fails on the stray carriage returns instead of on real syntax errors.
    result = subprocess.run(["bash", "-n"], input=script.encode(), capture_output=True, check=False)
    assert result.returncode == 0, f"{name}.txt: {result.stderr.decode(errors='replace')}"


# --- command line behaviour ---------------------------------------------------


def test_show_all_examples(capsys):
    code, out, _ = run(capsys, "find")
    assert code == 0
    assert out.startswith("find - ")
    assert "find ." in out


def test_filter_by_keyword(capsys):
    code, out, _ = run(capsys, "find", "size")
    assert code == 0
    blocks = out.strip().split("\n\n")[1:]  # first block is the header
    assert blocks
    assert all("size" in block.lower() for block in blocks)


def test_options_can_come_after_keywords(capsys):
    code, out, _ = run(capsys, "tar", "extract", "--oneline")
    assert code == 0 and out.strip()


def test_oneline_output(capsys):
    code, out, _ = run(capsys, "grep", "--oneline")
    lines = out.strip().splitlines()
    assert code == 0 and lines
    assert all("  # " in line for line in lines)


def test_search_every_command(capsys):
    code, out, _ = run(capsys, "-s", "port")
    assert code == 0
    assert "ss - " in out and "nc - " in out


def test_list(capsys):
    code, out, _ = run(capsys, "--list")
    assert code == 0
    assert all(name in out for name in NAMES)


def test_unknown_command_suggests_a_close_match(capsys):
    code, _, err = run(capsys, "gerp")
    assert code == 1
    assert "grep" in err


def test_no_matching_keyword(capsys):
    code, _, err = run(capsys, "find", "no-such-keyword-anywhere")
    assert code == 1
    assert "No 'find' examples match" in err


def test_help(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "barem find size" in out
    assert "available commands" in out


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert cli.__version__ in capsys.readouterr().out


# --- shell completion ---------------------------------------------------------


def complete(capsys, *words):
    """Ask for candidates the way the completion scripts do, on every TAB."""
    code = cli.main(["--complete", *words])
    out, _ = capsys.readouterr()
    return code, out.split()


def test_complete_command_names(capsys):
    code, got = complete(capsys, "doc")
    assert code == 0
    assert got == ["docker"]


def test_complete_offers_every_command_when_no_word_is_typed_yet(capsys):
    _, got = complete(capsys, "")
    assert got == NAMES


def test_complete_keywords_of_the_command_on_the_line(capsys):
    _, got = complete(capsys, "tar", "extr")
    assert "extract" in got
    assert all(word.startswith("extr") for word in got)


def test_complete_offers_subcommands(capsys):
    """The word after the command name, e.g. `git rebase`, is worth offering."""
    _, got = complete(capsys, "git", "reb")
    assert "rebase" in got


def test_complete_skips_keywords_already_on_the_line(capsys):
    _, before = complete(capsys, "tar", "ex")
    _, after = complete(capsys, "tar", "extract", "ex")
    assert "extract" in before
    assert "extract" not in after


def test_complete_options(capsys):
    _, got = complete(capsys, "--no")
    assert got == ["--no-bars", "--no-color", "--no-header", "--no-summary", "--no-wrap"]


#: Every option the CLI accepts, in the order completion offers them.
#: Spelled out so adding or renaming a flag has to be a deliberate change.
PUBLIC_OPTIONS = sorted(
    [
        # example lookup
        "--completion",
        "--help",
        "--list",
        "--no-color",
        "--oneline",
        "--search",
        "--version",
        "-1",
        "-V",
        "-h",
        "-l",
        "-s",
        # table mode
        "--as",
        "--ascii",
        "--bar-width",
        "--box",
        "--cards",
        "--clean",
        "--cols",
        "--crit",
        "--format",
        "--input",
        "--max-width",
        "--no-bars",
        "--no-header",
        "--no-summary",
        "--profiles",
        "--raw",
        "--relative",
        "--sort",
        "--symbols",
        "--top",
        "--warn",
        "--watch",
        "--where",
        "--width",
        # style choices
        "--style",
        "--styles",
        "--pct",
        "--pad",
        "--no-wrap",
        # barem help
        "--all",
    ]
)


def test_complete_offers_every_public_option(capsys):
    """--complete itself stays hidden: it is plumbing, not for typing by hand."""
    _, got = complete(capsys, "-")
    assert got == PUBLIC_OPTIONS
    assert "--complete" not in got


def test_complete_search_looks_at_every_command(capsys):
    _, got = complete(capsys, "-s", "certifi")
    assert "certificate" in got  # from openssl.txt


def test_complete_without_a_match_prints_nothing(capsys):
    code, got = complete(capsys, "no-such-word-anywhere")
    assert code == 0
    assert got == []


@pytest.mark.parametrize("shell", cli.COMPLETION_SHELLS)
def test_completion_script_is_printed(capsys, shell):
    code = cli.main(["--completion", shell])
    out, _ = capsys.readouterr()
    assert code == 0
    assert "_barem" in out
    assert "--complete" in out  # the script asks the CLI for its candidates


def test_completion_rejects_an_unknown_shell():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--completion", "csh"])
    assert exc.value.code == 2


@pytest.mark.parametrize("shell", cli.COMPLETION_SHELLS)
def test_completion_script_is_valid_shell_syntax(capsys, shell):
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} is not installed")
    cli.main(["--completion", shell])
    script = capsys.readouterr().out
    result = subprocess.run([shell, "-n"], input=script.encode(), capture_output=True, check=False)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
