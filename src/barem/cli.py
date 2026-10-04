"""Command-line interface for barem.

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
from . import table as table_mod

EXTENSION = ".txt"

#: `barem help` runs the diagnosis; `--help` still prints the usage text.
DIAGNOSE_WORDS = ("help", "check", "doctor")

#: Flags whose value may legitimately start with a dash: `--sort -size` means
#: descending. argparse would read that as another option, so these are
#: rewritten to `--sort=-size` before parsing.
DASH_VALUE_FLAGS = ("--sort", "--cols", "--where", "--as")

#: Flags that mean the user wants table mode even without a pipe in sight.
TABLE_INTENT = (
    "profile",
    "sort",
    "top",
    "cols",
    "where",
    "export",
    "box",
    "ascii",
    "cards",
    "input_format",
    "raw",
    "no_header",
    "no_summary",
    "symbols",
    "relative",
)

DESCRIPTION = """\
Real-world, copy-paste-ready examples for Linux commands.

Every example is a short description followed by the command itself,
so the output is easy to read, copy and grep."""

USAGE_EXAMPLES = """\
examples:
  barem find                   all examples for find
  barem find size              only examples that mention "size"
  barem tar extract gz         several keywords: all of them must match
  barem -s port                search the examples of every command
  barem -l                     list available commands
  barem find -1 | grep perm    one example per line, grep-friendly
  barem find | grep -A1 perm   plain grep: description + command"""


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
    return resources.files("barem").joinpath("examples")


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
    lines += ["", "Usage: barem <command> [keyword ...]"]
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


COMPLETION_SHELLS = ("bash", "zsh")


def completion_script(shell: str) -> str:
    """The completion script for `shell`, shipped inside the package."""
    # One joinpath per segment: on Python 3.9 a zipped package hands back a
    # zipfile.Path, whose joinpath only took a single argument back then.
    path = resources.files("barem").joinpath("completions").joinpath(f"barem.{shell}")
    return path.read_text(encoding="utf-8").rstrip("\n")


def option_names() -> list[str]:
    """Every option the parser accepts, so completion never drifts from it."""
    return sorted(option for action in build_parser()._actions for option in action.option_strings)


def vocabulary(sheet: Sheet) -> list[str]:
    """Keywords worth offering for one command.

    Keywords match the start of a word, so the candidates that help are the
    words someone would actually type: the words of the descriptions, the long
    options of the commands (`--exclude`) and whatever follows the command
    name (`git rebase`, `docker compose`). Paths and hosts are left out.
    """
    words: set[str] = set()
    for example in sheet.examples:
        words.update(re.findall(r"[a-z][a-z0-9-]{2,}", example.description.lower()))
        for command in example.commands:
            words.update(re.findall(r"--[a-z][a-z0-9-]+", command))
            tokens = command.split()
            for token, following in zip(tokens, tokens[1:]):
                if token == sheet.name and re.fullmatch(r"[a-z][a-z0-9-]{2,}", following):
                    words.add(following)
    return sorted(words)


def completion_candidates(words: list[str]) -> list[str]:
    """Candidates for the last of `words`, the word currently being typed.

    `words` is everything after the program name, so ["doc"] while typing a
    command name and ["tar", "extr"] while typing a keyword for tar.
    """
    partial = words[-1] if words else ""
    earlier = words[:-1]

    if partial.startswith("-"):
        return [option for option in option_names() if option.startswith(partial)]

    names = available()
    if any(word in ("-s", "--search") for word in earlier):
        pool = {word for name in names for word in vocabulary(load(name))}
    else:
        command = next((word for word in earlier if word in names), None)
        if command is None:
            return [name for name in names if name.startswith(partial)]
        pool = set(vocabulary(load(command)))

    # Don't offer a keyword that is already on the line.
    return sorted(word for word in pool - set(earlier) if word.startswith(partial))


def build_parser() -> argparse.ArgumentParser:
    commands = textwrap.fill(
        " ".join(available()), width=72, initial_indent="  ", subsequent_indent="  "
    )
    parser = argparse.ArgumentParser(
        prog="barem",
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
    parser.add_argument(
        "--completion",
        choices=COMPLETION_SHELLS,
        metavar="SHELL",
        help=f"print a completion script for {' or '.join(COMPLETION_SHELLS)}",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    _add_table_arguments(parser)
    return parser


def _add_table_arguments(parser: argparse.ArgumentParser) -> None:
    """Flags for table mode, which reads piped command output.

    Kept in their own group so `--help` does not mix them with the example
    lookup options, which are what most people came for.
    """
    group = parser.add_argument_group(
        "table mode",
        "format piped output: df -h | barem, or barem run df -h",
    )
    group.add_argument(
        "--as",
        dest="profile",
        metavar="NAME",
        help="force a profile, e.g. --as df (see --profiles)",
    )
    group.add_argument("--profiles", action="store_true", help="list the known command profiles")
    group.add_argument(
        "--sort", metavar="COL", help="sort by a column by real value; prefix - for descending"
    )
    group.add_argument("--top", type=int, metavar="N", help="keep only the first N rows")
    group.add_argument("--cols", metavar="LIST", help="choose and order columns, comma separated")
    group.add_argument(
        "--where",
        action="append",
        default=[],
        metavar="EXPR",
        help="keep rows matching 'col > value'; also < >= <= == != ~",
    )
    group.add_argument(
        "--format",
        dest="export",
        choices=table_mod.FORMATS,
        metavar="STYLE",
        help="export instead of rendering: md, csv, tsv or json",
    )
    style = group.add_mutually_exclusive_group()
    style.add_argument(
        "--box", action="store_true", help="draw borders around every cell (default)"
    )
    style.add_argument("--clean", action="store_true", help="no borders, just an underlined header")
    style.add_argument("--ascii", action="store_true", help="no Unicode, for old terminals")
    style.add_argument("--cards", action="store_true", help="one block per row, for narrow windows")
    group.add_argument("--width", type=int, metavar="N", help="assume this terminal width")
    group.add_argument(
        "--max-width",
        type=int,
        metavar="N",
        help="never use more than this many columns (default 160)",
    )
    group.add_argument("--no-bars", action="store_true", help="numbers without usage bars")
    group.add_argument(
        "--bar-width",
        type=int,
        default=10,
        metavar="N",
        help="cells in a usage bar (default 10, 0 to disable)",
    )
    group.add_argument("--symbols", action="store_true", help="add a symbol to status cells")
    group.add_argument(
        "--warn",
        type=float,
        default=70.0,
        metavar="N",
        help="percentage at which a value counts as worth watching",
    )
    group.add_argument(
        "--crit",
        type=float,
        default=90.0,
        metavar="N",
        help="percentage at which a value counts as critical",
    )
    group.add_argument(
        "--relative", action="store_true", help="show durations as '3 min ago' instead of '3m'"
    )
    group.add_argument(
        "--input",
        dest="input_format",
        choices=table_mod.detect.INPUT_FORMATS,
        metavar="FMT",
        help="force the input format instead of detecting it",
    )
    group.add_argument("--no-header", action="store_true", help="the input has no header row")
    group.add_argument("--no-summary", action="store_true", help="omit the line under the table")
    group.add_argument("--raw", action="store_true", help="print the input unchanged")
    group.add_argument(
        "--all",
        dest="all_checks",
        action="store_true",
        help="with `barem help`, list the checks that passed as well",
    )
    group.add_argument(
        "--watch", type=float, metavar="SECONDS", help="with 'run', re-run and redraw every SECONDS"
    )


def join_dash_values(argv: list[str]) -> list[str]:
    """Rewrite `--sort -size` as `--sort=-size`.

    A descending sort is spelled with a leading dash, which argparse would
    otherwise treat as the start of another option.
    """
    out: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if (
            token in DASH_VALUE_FLAGS
            and index + 1 < len(argv)
            and argv[index + 1].startswith("-")
            and argv[index + 1] != "--"
        ):
            out.append(f"{token}={argv[index + 1]}")
            index += 2
            continue
        out.append(token)
        index += 1
    return out


def table_options(args: argparse.Namespace) -> table_mod.Options:
    """Translate parsed arguments into table-mode options."""
    # Borders are the default; --clean, --ascii and --cards each replace them.
    style = "box"
    if args.clean:
        style = "clean"
    elif args.ascii:
        style = "ascii"
    elif args.cards:
        style = "cards"
    return table_mod.Options(
        profile=args.profile,
        input_format=args.input_format,
        style=style,
        export=args.export,
        width=args.width,
        max_width=args.max_width,
        bars=not args.no_bars,
        bar_width=args.bar_width,
        symbols=args.symbols,
        warn=args.warn,
        crit=args.crit,
        color=False if args.no_color else None,
        unicode=not args.ascii,
        summary=not args.no_summary,
        sort=args.sort,
        top=args.top,
        columns=[c.strip() for c in (args.cols or "").split(",") if c.strip()],
        where=list(args.where or []),
        relative=args.relative,
        no_header=args.no_header,
        raw=args.raw,
    )


def wants_table(args: argparse.Namespace) -> bool:
    """Whether to read standard input and format it as a table.

    A command name always means the example lookup, which is what the tool
    was before table mode existed. Otherwise a table flag or a pipe on
    standard input is taken as the intent.
    """
    if args.command or args.list or args.search or args.completion or args.profiles:
        return False
    if any(getattr(args, name, None) for name in TABLE_INTENT):
        return True
    try:
        return not sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def read_stdin() -> str | None:
    """Read piped input, or None when there is nothing readable."""
    try:
        return sys.stdin.read()
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    except Exception:
        # pytest replaces stdin with an object that refuses to be read.
        return None


def run_diagnose(argv: list[str]) -> int:
    """`barem help`: run the first-try diagnostics and report what is off."""
    from . import diagnose

    parser = build_parser()
    args = parser.parse_args(join_dash_values(argv))
    results = diagnose.run_checks()
    table = diagnose.build_table(results, show_all=args.all_checks)

    options = table_options(args)
    if not table.rows and not args.all_checks:
        # Nothing to show is the good case, so say so rather than printing an
        # empty table. The summary already opens with the verdict.
        style = Style(colors_enabled(args.no_color))
        emit(" " + style.title(table.summary))
        return diagnose.exit_code(results)

    emit(table_mod.render_table(table, options))
    return diagnose.exit_code(results)


def run_wrapper(argv: list[str]) -> int:
    """`barem run df -h`: run the command, then format its output."""
    from .table import runner

    own, command = runner.split_command(argv)
    parser = build_parser()
    args = parser.parse_args(join_dash_values(own))
    options = table_options(args)
    hint = command[0] if command else None
    if args.watch:
        return runner.watch(command, options, args.watch, profile_hint=hint)
    return runner.run_once(command, options, profile_hint=hint)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # The shell calls `--complete` on every TAB with raw, half-typed words
    # ("--no-c", "-"), which argparse would try to read as options, so handle
    # it before parsing. It stays out of --help on purpose: it is the plumbing
    # behind `--completion`, not something to type by hand.
    if argv and argv[0] == "--complete":
        found = completion_candidates(argv[1:])
        return emit("\n".join(found)) if found else 0

    # `run` wraps a command, so everything after it belongs to that command
    # and must not be parsed as ours.
    if argv and argv[0] == "run":
        return run_wrapper(argv[1:])

    # `barem help` is the diagnosis, not the usage text -- that stays on
    # `--help`. `check` and `doctor` do the same thing, for whichever word
    # comes to mind first.
    if argv and argv[0] in DIAGNOSE_WORDS:
        return run_diagnose(argv[1:])

    parser = build_parser()
    args = parser.parse_intermixed_args(join_dash_values(argv))
    style = Style(colors_enabled(args.no_color))

    if args.search and args.command:
        parser.error("use either a command or --search, not both")

    if args.completion:
        return emit(completion_script(args.completion))

    if args.profiles:
        names = table_mod.profile_names()
        lines = [style.title(f"Known table profiles ({len(names)}):"), ""]
        lines += [f"  {style.command(name)}" for name in names]
        lines += ["", "Force one with: df -h | barem --as df"]
        return emit("\n".join(lines))

    if wants_table(args):
        text = read_stdin()
        if text is None:
            parser.print_help()
            return 0
        if not text.strip():
            return 0
        rendered = table_mod.format_text(text, table_options(args))
        return emit(rendered) if rendered else 0

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
        print("Run 'barem --list' to see all commands.", file=sys.stderr)
        return 1

    sheet = load(name)
    examples = [example for example in sheet.examples if example.matches(args.keywords)]
    if not examples:
        print(f"No '{name}' examples match: {' '.join(args.keywords)}", file=sys.stderr)
        return 1

    return emit(render(sheet, examples, style, args.oneline))
