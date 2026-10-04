"""Shared pytest configuration.

`--update-golden` rewrites the stored table renderings after an intended
layout change, so a diff in the golden files is always a real regression and
never a chore.
"""


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="rewrite tests/golden/* from the current renderer output",
    )
