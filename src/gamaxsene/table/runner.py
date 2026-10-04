"""Wrapper mode: run the command ourselves, so its name is known.

A pipe hands us bytes and no command name, so the profile has to be guessed
from the header. `gamaxsene run df -i` removes the guess, and is also what
makes `--watch` possible, since watching means re-running.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

from . import Options, format_text

#: Table-mode flags that take a value. Needed to find where the wrapped
#: command starts, since `gamaxsene run df -h` must not have its -h eaten.
VALUE_FLAGS = frozenset(
    {
        "--as",
        "--sort",
        "--top",
        "--cols",
        "--where",
        "--format",
        "--input",
        "--width",
        "--max-width",
        "--bar-width",
        "--warn",
        "--crit",
        "--watch",
    }
)


def split_command(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Separate our own flags from the command to run.

    Everything up to the first bare word belongs to us; that word and the
    rest are the command, so its own options are passed through untouched.
    """
    own: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if not token.startswith("-"):
            break
        own.append(token)
        if token in VALUE_FLAGS and index + 1 < len(tokens):
            own.append(tokens[index + 1])
            index += 1
        index += 1
    return own, tokens[index:]


def capture(command: list[str]) -> tuple[str, str, int]:
    """Run a command and capture its output as text."""
    if not command:
        return "", "nothing to run", 2
    if shutil.which(command[0]) is None:
        return "", f"command not found: {command[0]}", 127
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError as error:
        return "", f"could not run {command[0]}: {error}", 126
    return done.stdout, done.stderr, done.returncode


def run_once(command: list[str], options: Options, profile_hint: str | None = None) -> int:
    """Run the command once and print its output as a table."""
    text, err, code = capture(command)
    if err and not text:
        print(err.rstrip("\n"), file=sys.stderr)
        return code or 1
    if err:
        print(err.rstrip("\n"), file=sys.stderr)
    if options.profile is None and profile_hint:
        options.profile = profile_hint
    rendered = format_text(text, options)
    if rendered:
        print(rendered)
    return code


def watch(
    command: list[str], options: Options, seconds: float, profile_hint: str | None = None
) -> int:
    """Re-run the command and redraw in place until interrupted."""
    seconds = max(0.2, seconds)
    if options.profile is None and profile_hint:
        options.profile = profile_hint
    header_prefix = " ".join(command)
    try:
        while True:
            text, err, _code = capture(command)
            rendered = format_text(text, options) if text else (err or "")
            # Home the cursor and clear to the end of the screen, which
            # redraws without the flicker of a full clear.
            sys.stdout.write("\033[H\033[J")
            stamp = time.strftime("%H:%M:%S")
            sys.stdout.write(f" every {seconds:g}s · {header_prefix} · {stamp}\n\n")
            sys.stdout.write(rendered.rstrip("\n") + "\n")
            sys.stdout.flush()
            time.sleep(seconds)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        return 0
