"""Tests that keep the docs honest.

The README lists every command with its example count, and the install
instructions name a version. All of that is easy to forget when a command is
added or the version is bumped, so it is checked here instead.
"""

import re
from pathlib import Path

import pytest

from barem import __version__, cli

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"

# A row of one of the "Available commands" tables: | `ls` | 32 | List ... |
# The name may contain a hyphen, as in `ssh-keygen`.
TABLE_ROW = re.compile(r"^\| `([a-z][a-z0-9-]*)` \| (\d+) \|", re.MULTILINE)

pytestmark = pytest.mark.skipif(not README.is_file(), reason="not running from a source checkout")


@pytest.fixture(scope="module")
def readme():
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sheets():
    return {name: cli.load(name) for name in cli.available()}


def test_every_command_has_a_table_row(readme, sheets):
    listed = {name for name, _ in TABLE_ROW.findall(readme)}
    assert not set(sheets) - listed, "add these commands to a README table"


def test_no_table_row_names_a_command_that_does_not_exist(readme, sheets):
    listed = {name for name, _ in TABLE_ROW.findall(readme)}
    assert not listed - set(sheets), "these README rows have no example file"


def test_table_counts_match_the_example_files(readme, sheets):
    wrong = {
        name: (int(count), len(sheets[name].examples))
        for name, count in TABLE_ROW.findall(readme)
        if name in sheets and len(sheets[name].examples) != int(count)
    }
    assert not wrong, f"README says (claimed, actual): {wrong}"


def test_table_summaries_match_the_example_files(readme, sheets):
    missing = [sheet.title for sheet in sheets.values() if sheet.title not in readme]
    assert not missing, f"summaries changed but the README did not: {missing}"


def test_headline_totals_match(readme, sheets):
    match = re.search(r"ships \*\*(\d+) commands\*\* and \*\*([\d,]+) examples\*\*", readme)
    assert match, "the README no longer states its totals in the expected words"
    commands, examples = match.groups()
    total = sum(len(sheet.examples) for sheet in sheets.values())
    assert int(commands) == len(sheets)
    assert int(examples.replace(",", "")) == total


def test_readme_installs_the_current_version(readme):
    """The `pipx install ...@vX.Y.Z` line has to name a tag that will exist."""
    tags = set(re.findall(r"\.git@(v[\d.]+)", readme))
    assert tags == {f"v{__version__}"}


@pytest.mark.skipif(not CHANGELOG.is_file(), reason="no CHANGELOG.md")
def test_changelog_documents_the_current_version():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert f"## [{__version__}]" in text, f"CHANGELOG.md has no section for {__version__}"
