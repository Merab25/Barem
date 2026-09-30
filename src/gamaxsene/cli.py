"""Command-line interface for gamaxsene.

Each Linux command has one text file in the `examples/` folder, for example
`examples/find.txt`. This module finds those files, parses them into
examples, filters them by keywords and prints them.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from importlib import resources

from . import __version__

EXTENSION = ".txt"

DESCRIPTION = """\
Real-world, copy-paste-ready examples for Linux commands.

Every example is a short description followed by the command itself,
so the output is easy to read, copy and grep."""

USAGE_EXAMPLES = """\
examples:
  gamaxsene find                   all examples for find
  gamaxsene find size              only examples that mention "size"
  gamaxsene tar extract gz         several keywords: all of them must match
  gamaxsene -s port                search the examples of every command
  gamaxsene -l                     list available commands
  gamaxsene find -1 | grep perm    one example per line, grep-friendly
  gamaxsene find | grep -A1 perm   plain grep: description + command"""


@dataclass
class Example:
    """One example: a description and one or more command lines."""

    description: str
    commands: list[str] = field(default_factory=list)

    def matches(self, keywords: list[str]) -> bool:
        """True if every keyword appears in the description or the commands.

        Case-insensitive, and a keyword must match the start of a word:
        "port" finds "port" and "ports" but not "export" or "report".
        """
        haystack = " ".join([self.description, *self.commands]).lower()
        return all(
            re.search(r"(?<![a-z0-9])" + re.escape(keyword.lower()), haystack)
            for keyword in keywords
        )


@dataclass
class Sheet:
    """All examples for one command, parsed from one file."""

    name: str
    title: str
    examples: list[Example]


def examples_dir():
    """Location of the bundled example files, wherever the package is installed."""
    return resources.files("gamaxsene").joinpath("examples")


def available() -> list[str]:
    """Names of all commands that have an example file."""
    return sorted(
        entry.name[: -len(EXTENSION)]
        for entry in examples_dir().iterdir()
        if entry.name.endswith(EXTENSION)
    )


def parse(name: str, text: str) -> Sheet:
    """Parse the text of an example file.

    File format:
        ## One-line summary of the command
        # Description of an example
        the command itself
        (blank lines are ignored)

    Several command lines under one description belong to the same example.
    """
    title = ""
    examples: list[Example] = []
    current: Example | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("##"):
            title = line.lstrip("#").strip()
        elif line.startswith("#"):
            description = line[1:].strip()
            if current is not None and not current.commands:
                # Two description lines in a row: treat them as one description.
                current.description = f"{current.description} {description}".strip()
            else:
                current = Example(description)
                examples.append(current)
        else:
            if current is None:
                current = Example("")
                examples.append(current)
            current.commands.append(line)

    return Sheet(name, title, [example for example in examples if example.commands])


def load(name: str) -> Sheet:
    path = examples_dir().joinpath(name + EXTENSION)
    return parse(name, path.read_text(encoding="utf-8"))


class Style:
    """Adds ANSI colors, or does nothing when colors are disabled."""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _paint(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def title(self, text: str) -> str:
        return self._paint("1;33", text)

    def description(self, text: str) -> str:
        return self._paint("36", text)

    def command(self, text: str) -> str:
        return self._paint("1", text)

    def muted(self, text: str) -> str:
        return self._paint("2", text)


def colors_enabled(disabled_by_flag: bool) -> bool:
    """Colors only when writing to a real terminal, so pipes and grep get plain text."""
    if disabled_by_flag or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def render(sheet: Sheet, examples: list[Example], style: Style, oneline: bool = False) -> str:
    if oneline:
        return "\n".join(
            f"{style.command(command)}  {style.description('# ' + example.description)}"
            for example in examples
            for command in example.commands
        )

    heading = f"{sheet.name} - {sheet.title}" if sheet.title else sheet.name
    lines = [style.title(heading), ""]
    for example in examples:
        lines.append(style.description("# " + example.description))
        lines.extend(style.command(command) for command in example.commands)
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def render_list(style: Style) -> str:
    names = available()
    width = max(len(name) for name in names)
    lines = [style.title(f"Available commands ({len(names)}):"), ""]
    for name in names:
        sheet = load(name)
        count = style.muted(f"({len(sheet.examples)})")
        lines.append(f"  {style.command(name.ljust(width))}  {sheet.title} {count}")
    lines += ["", "Usage: gamaxsene <command> [keyword ...]"]
    return "\n".join(lines)


def search(keywords: list[str], style: Style, oneline: bool) -> tuple[str, int]:
    """Search the examples of every command. Returns (output, number of matches)."""
    blocks = []
    total = 0
    for name in available():
        sheet = load(name)
        hits = [example for example in sheet.examples if example.matches(keywords)]
        if hits:
            total += len(hits)
            blocks.append(render(sheet, hits, style, oneline))
    return ("\n" if oneline else "\n\n").join(blocks), total


def emit(text: str) -> int:
    """Print output, staying quiet if the reader (e.g. `head`) closes the pipe early."""
    try:
        print(text)
        sys.stdout.flush()
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    return 0


def build_parser() -> argparse.ArgumentParser:
    commands = textwrap.fill(
        " ".join(available()), width=72, initial_indent="  ", subsequent_indent="  "
    )
    parser = argparse.ArgumentParser(
        prog="gamaxsene",
        description=DESCRIPTION,
        epilog=f"{USAGE_EXAMPLES}\n\navailable commands:\n{commands}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?", help="command to show examples for, e.g. find")
    parser.add_argument(
        "keywords", nargs="*", help="only show examples that contain all of these words"
    )
    parser.add_argument("-l", "--list", action="store_true", help="list all available commands")
    parser.add_argument(
        "-s", "--search", nargs="+", metavar="KEYWORD", help="search the examples of every command"
    )
    parser.add_argument(
        "-1",
        "--oneline",
        action="store_true",
        help="print each example on one line: command  # description",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="disable colors (also: NO_COLOR=1 env variable)"
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_intermixed_args(argv)
    style = Style(colors_enabled(args.no_color))

    if args.search and args.command:
        parser.error("use either a command or --search, not both")

    if args.list:
        return emit(render_list(style))

    if args.search:
        output, total = search(args.search, style, args.oneline)
        if not total:
            print(f"No examples found for: {' '.join(args.search)}", file=sys.stderr)
            return 1
        return emit(output)

    if not args.command:
        parser.print_help()
        return 0

    name = args.command.lower()
    names = available()
    if name not in names:
        print(f"No examples for '{args.command}' yet.", file=sys.stderr)
        suggestions = difflib.get_close_matches(name, names, n=3)
        if suggestions:
            print(f"Did you mean: {', '.join(suggestions)}?", file=sys.stderr)
        print("Run 'gamaxsene --list' to see all commands.", file=sys.stderr)
        return 1

    sheet = load(name)
    examples = [example for example in sheet.examples if example.matches(args.keywords)]
    if not examples:
        print(f"No '{name}' examples match: {' '.join(args.keywords)}", file=sys.stderr)
        return 1

    return emit(render(sheet, examples, style, args.oneline))
