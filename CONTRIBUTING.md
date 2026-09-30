# Contributing to gamaxsene

Thanks for helping. The most useful contribution is usually a new command file
or a better example, and neither needs any Python.

## Setting up

```bash
git clone https://github.com/Merab25/Gamaxsene.git
cd Gamaxsene
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Adding or improving examples

Each command is one text file in `src/gamaxsene/examples/`, named after the
command. The format and the house style are described in the README, under
[Example file format](README.md#example-file-format) and
[Adding a command](README.md#adding-a-command). In short:

- `## summary` on the first line, then `# description` / command pairs.
- Aim for about 30 examples, most common use first.
- Use realistic values (`/var/log/nginx/access.log`, `user@server`) rather than
  `<placeholder>` soup, so an example can be copied and edited quickly.
- Keep each command on one line.

If you add a command, also add its row to the matching table in the README. A
test compares those tables against the files, so a missing or stale row fails
the build.

## Before opening a pull request

```bash
pytest                 # parser, example files, CLI and completion
ruff check .           # lint
ruff format .          # format
```

CI runs the same three on Python 3.9 through 3.13, builds the wheel and sdist,
installs the wheel and smoke-tests the CLI and the bash completion script.

The tests check that every example file has a summary, has at least 20 examples,
and that every command parses as valid shell (`bash -n`). They do not run the
commands.

## Safety

Examples are copy-pasted by people at a terminal, sometimes as root. Prefer the
non-destructive form, and when an example does change or delete something, say
so in its description.
