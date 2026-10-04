"""Golden-file tests: every fixture rendered at several widths.

A layout change then shows up as a readable diff rather than as a vague
failure. After an intended change, regenerate with:

    pytest --update-golden

and read the diff in `git diff tests/golden/` before committing it.
"""

from pathlib import Path

import pytest

from gamaxsene.table import Options, format_text
from gamaxsene.table.width import display_width

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"

#: 40 lands in card mode, 60 forces shrinking and dropping, 80 is the common
#: default and 120 is a wide window where everything fits.
WIDTHS = (40, 60, 80, 120)
CASES = [
    *[
        (name, width, "clean")
        for name in sorted(p.stem for p in FIXTURES.glob("*.txt"))
        for width in WIDTHS
    ],
    ("df-h", 80, "box"),
    ("df-h", 80, "ascii"),
    ("df-h", 80, "md"),
    ("kubectl-pods", 80, "box"),
    ("ps-aux", 100, "clean"),
]


def render(name: str, width: int, style: str) -> str:
    text = (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")
    if style in ("md", "csv", "tsv", "json"):
        options = Options(width=width, color=False, export=style)
    else:
        options = Options(width=width, color=False, style=style)
    return format_text(text, options)


@pytest.mark.parametrize(("name", "width", "style"), CASES)
def test_golden(name, width, style, request):
    expected_path = GOLDEN / f"{name}-{style}-{width}.txt"
    actual = render(name, width, style)

    if request.config.getoption("--update-golden"):
        GOLDEN.mkdir(exist_ok=True)
        expected_path.write_text(actual + "\n", encoding="utf-8", newline="\n")
        pytest.skip(f"wrote {expected_path.name}")

    if not expected_path.is_file():
        pytest.fail(f"missing golden file {expected_path.name}; run pytest --update-golden")

    expected = expected_path.read_text(encoding="utf-8").rstrip("\n")
    assert actual == expected


@pytest.mark.parametrize(("name", "width", "style"), CASES)
def test_golden_respects_its_width(name, width, style):
    """The width invariant, checked on exactly what the golden files store."""
    if style in ("md", "csv", "tsv", "json"):
        return  # export formats are not width-constrained
    for line in render(name, width, style).splitlines():
        assert display_width(line) <= width
