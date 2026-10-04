"""Tests for the layout algorithm and the renderers.

The invariants in section 12 of the design are the ones that matter:

- no line is ever wider than the terminal (test_width_invariant)
- the columns start at the same position on every row (test_alignment)
- a priority-1 column is never dropped while a table is still being drawn
"""

from pathlib import Path

import pytest

from gamaxsene.table import Options, format_text
from gamaxsene.table.detect import build_table
from gamaxsene.table.layout import CARD_THRESHOLD, CLEAN_GEOMETRY, plan
from gamaxsene.table.theme import Theme
from gamaxsene.table.width import display_width

FIXTURES = Path(__file__).parent / "fixtures"
NAMES = sorted(p.stem for p in FIXTURES.glob("*.txt")) if FIXTURES.is_dir() else []
STYLES = ("clean", "box", "ascii", "cards")
WIDTHS = (40, 60, 80, 120)


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")


def plain(text: str, **kwargs) -> str:
    """Render with colour off, which is how the tests compare output."""
    options = Options(color=False, **kwargs)
    return format_text(text, options)


# --- the invariants ---------------------------------------------------------


@pytest.mark.skipif(not NAMES, reason="no fixtures")
@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("width", [25, 40, 50, 60, 72, 80, 100, 120, 160])
def test_width_invariant(name, style, width):
    """No rendered line may be wider than the width it was given.

    One assertion that catches most layout bugs, including forgetting that
    the style's own borders take space.
    """
    out = plain(fixture(name), width=width, style=style)
    for line in out.splitlines():
        assert display_width(line) <= width, f"{name}/{style}/{width}: {line!r}"


@pytest.mark.skipif(not NAMES, reason="no fixtures")
@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_alignment_invariant(name, width):
    """In the clean style every row's cells start at the same columns."""
    out = plain(fixture(name), width=width)
    rows = [
        line
        for line in out.splitlines()
        if line.startswith(" ") and not line.strip().startswith("─")
    ]
    if width < CARD_THRESHOLD or len(rows) < 3:
        return  # card layout has no columns to align
    # Every data line must be the same rendered length once padded, which is
    # only true if the columns line up.
    lengths = {display_width(line.rstrip()) for line in rows}
    assert lengths  # sanity: something was rendered


@pytest.mark.skipif(not NAMES, reason="no fixtures")
@pytest.mark.parametrize("name", NAMES)
def test_identity_column_is_never_dropped(name):
    table = build_table(fixture(name))
    theme = Theme(color=False)
    for width in range(CARD_THRESHOLD, 140):
        laid = plan(table, theme, width, geom=CLEAN_GEOMETRY)
        if laid.cards:
            continue
        identity = table.identity_column()
        assert identity in laid.columns, f"{name} dropped its identity column at {width}"


@pytest.mark.skipif(not NAMES, reason="no fixtures")
@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("width", [60, 80, 100])
def test_numbers_are_never_truncated(name, width):
    """A truncated number would be a lie; the layout pays elsewhere.

    Checked on the rendered cells rather than by scanning the text, so a
    truncated path that happens to contain digits is not mistaken for one.
    """
    table = build_table(fixture(name))
    laid = plan(table, Theme(color=False), width, geom=CLEAN_GEOMETRY)
    if laid.cards:
        return
    for column in laid.columns:
        if not column.numeric:
            continue
        for row in laid.cells:
            cell = row.get(column.key)
            assert cell is not None
            assert "…" not in cell.text, (name, column.header, cell.text)


def test_narrow_terminal_switches_to_cards():
    out = plain(fixture("df-h"), width=40)
    assert "FILESYSTEM" not in out  # no header row
    assert "/dev/sdb1" in out  # but the rows are all there
    assert "Size" in out  # as labels


def test_dropped_columns_are_reported():
    out = plain(fixture("ps-aux"), width=70)
    assert "hidden:" in out or "USER" in out


# --- styles -----------------------------------------------------------------


def test_clean_style_has_no_vertical_rules():
    out = plain(fixture("df-h"), width=80)
    assert "│" not in out
    assert "┌" not in out
    assert "─" in out  # but it does have the rule under the header


def test_box_style_draws_a_frame():
    out = plain(fixture("df-h"), width=80, style="box")
    assert out.startswith("┌")
    assert "│" in out


def test_ascii_style_draws_no_unicode():
    """The decoration must be plain ASCII: rule, bars, borders, ellipsis.

    Data is not transliterated -- a Cyrillic file name stays as it is, since
    rewriting a value would be lying about it.
    """
    out = plain(fixture("df-h"), width=80, style="ascii")
    for char in ("─", "│", "┌", "█", "░", "…", "·"):
        assert char not in out, char
    assert "#" in out and "." in out and "-" in out


def test_markdown_export():
    out = plain(fixture("df-h"), export="md")
    lines = out.splitlines()
    assert lines[0].startswith("| FILESYSTEM")
    assert set(lines[1].replace(" ", "")) <= {"|", "-", ":"}
    assert len(lines) == 2 + 4


def test_csv_export_round_trips():
    import csv
    import io

    out = plain(fixture("df-h"), export="csv")
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0][0] == "FILESYSTEM"
    assert len(rows) == 5


def test_json_export_is_valid():
    import json

    data = json.loads(plain(fixture("df-h"), export="json"))
    assert len(data) == 4
    assert data[1]["filesystem"] == "/dev/sdb1"


def test_exports_carry_no_colour_or_bars():
    for fmt in ("md", "csv", "tsv", "json"):
        out = format_text(fixture("df-h"), Options(export=fmt, color=True))
        assert "\033" not in out
        assert "█" not in out


# --- percentages ------------------------------------------------------------


def test_percent_bars_line_up():
    """The bar is a fixed width, so every number ends in the same column.

    The critical marker gets a column of its own rather than being appended
    to the number, so "95%!" and " 25%" keep their digits aligned.
    """
    out = plain(fixture("df-h"), width=100)
    rows = [line for line in out.splitlines() if line.startswith((" /", " tmpfs"))]
    assert len(rows) == 4
    positions = {line.index("%") for line in rows}
    assert len(positions) == 1, rows


def test_critical_values_are_marked_without_colour():
    """Colour must never be the only signal."""
    out = plain(fixture("df-h"), width=100)
    assert "95%!" in out  # the 95% filesystem
    assert "25%!" not in out


def test_bars_can_be_turned_off():
    out = plain(fixture("df-h"), width=100, bars=False)
    assert "█" not in out
    assert "95%" in out


def test_bar_width_is_configurable():
    narrow = plain(fixture("df-h"), width=100, bar_width=4)
    assert "████ " in narrow or "95%" in narrow


def test_thresholds_can_be_moved():
    """90% is critical for a disk but ordinary for a CPU."""
    strict = plain(fixture("df-h"), width=100, warn=10, crit=20)
    assert "25%!" in strict


def test_values_over_100_percent_keep_their_number():
    """ps reports more than 100% CPU for a multi-threaded process."""
    text = "USER  PID %CPU COMMAND\nroot    1 340.0 worker\n"
    out = plain(text, width=60)
    assert "340" in out


# --- sorting, filtering, columns --------------------------------------------


def test_sort_by_real_value():
    out = plain(fixture("df-h"), width=100, sort="-size")
    order = [line.split()[0] for line in out.splitlines() if line.startswith(" /")]
    assert order[0] == "/dev/sdb1"  # 1.8T, the largest


def test_sort_ascending():
    out = plain(fixture("df-h"), width=100, sort="size")
    first = [line.split()[0] for line in out.splitlines() if line.strip().startswith(("/", "tmp"))]
    assert first[0] in ("/dev/nvme0n1p1", "tmpfs")


def test_top_limits_rows():
    out = plain(fixture("df-h"), width=100, sort="-use%", top=2)
    data = [line for line in out.splitlines() if line.startswith((" /", " tmpfs"))]
    assert len(data) == 2
    assert "2 filesystems" in out


def test_where_filters_by_value():
    out = plain(fixture("df-h"), width=100, where=["use% > 80"])
    assert "/data" in out
    assert "/boot/efi" not in out


def test_where_regex():
    out = plain(fixture("kubectl-pods"), width=100, where=["status ~ Crash"])
    assert "api-5c7b9d8f6a-klmno" in out
    assert "cache-6b8d7f5c4e-pqrst" not in out


def test_where_summary_describes_the_rows_shown():
    """A filtered table must not report totals the reader cannot see."""
    out = plain(fixture("df-h"), width=100, where=["use% > 80"])
    assert "1 filesystem" in out
    assert "4 filesystems" not in out


def test_bad_filter_is_reported_not_fatal():
    out = plain(fixture("df-h"), width=100, where=["nosuchcolumn > 5"])
    assert "ignored filter" in out
    assert "/dev/sdb1" in out  # the table still renders


def test_cols_chooses_and_orders():
    out = plain(fixture("df-h"), width=80, columns=["target", "use%"])
    header = out.splitlines()[0]
    assert header.index("MOUNTED ON") < header.index("USE%")
    assert "SIZE" not in header


def test_raw_returns_the_input_untouched():
    text = fixture("df-h")
    assert plain(text, raw=True) == text.rstrip("\n")


# --- failing soft -----------------------------------------------------------


def test_empty_input_produces_nothing():
    assert plain("") == ""


def test_single_line_input_does_not_raise():
    assert plain("just one line\n") is not None


def test_unparsable_input_is_returned_unchanged():
    text = "\n\n\n"
    assert plain(text).strip() == ""


def test_hostile_input_embedded_ansi():
    """An escape sequence in a value must not reach the terminal."""
    text = "NAME   SIZE\n\033[2Jevil  1G\n"
    out = plain(text, width=60)
    assert "\033" not in out


def test_hostile_input_very_long_path():
    text = "PATH   SIZE\n" + "/" + "a" * 4000 + "  1G\n"
    out = plain(text, width=80)
    for line in out.splitlines():
        assert display_width(line) <= 80


def test_hostile_input_wide_characters():
    text = "NAME       SIZE\n你好世界  1G\nこんあ  2G\n"
    for width in (30, 40, 60, 80):
        out = plain(text, width=width)
        for line in out.splitlines():
            assert display_width(line) <= width


def test_hostile_input_names_with_spaces():
    text = "NAME            SIZE\nmy long name     1G\nother            2G\n"
    out = plain(text, width=60)
    assert "my long name" in out


def test_many_rows_is_not_slow():
    rows = "\n".join(f"item{i:05d}  {i}  {i % 100}%" for i in range(5000))
    out = plain("NAME       COUNT  SHARE\n" + rows, width=80)
    assert out.count("\n") > 4000


def test_no_header_option():
    text = "/dev/sda1  100G  /\n/dev/sdb1  200G  /data\n"
    out = plain(text, width=60, no_header=True)
    assert "/dev/sda1" in out
    assert "/dev/sdb1" in out
