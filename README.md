# gamaxsene

[![CI](https://github.com/Merab25/Gamaxsene/actions/workflows/ci.yml/badge.svg)](https://github.com/Merab25/Gamaxsene/actions/workflows/ci.yml)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)

**Real-world Linux command examples, right in your terminal.**

`gamaxsene` (Georgian *გამახსენე* — "remind me") prints practical, copy-paste-ready examples for everyday Linux, networking and DevOps commands. Instead of scrolling through a long man page to remember how to exclude a folder in `find`, follow a service log in `journalctl` or forward a port with `ssh`, you ask:

```console
$ gamaxsene find size
```

```text
find - Search for files and directories by name, type, size, time and permissions

# Files bigger than 100 MB anywhere, hide permission errors
find / -type f -size +100M 2>/dev/null

# Files between 10 MB and 50 MB
find . -type f -size +10M -size -50M

# Stay on one filesystem (skip /proc, mounted disks)
find / -xdev -type f -size +500M 2>/dev/null
```

It currently ships **37 commands** and **1,236 examples** — about 30 per command, covering the options and flags you actually use at work.

## Features

- **Real-world examples**: realistic file names, paths and hosts instead of `<placeholder>` soup, ordered from the most common to the more advanced.
- **Description first, command second**: every example is a `# description` line followed by the command, so it reads like a well-commented script.
- **Keyword filtering**: `gamaxsene tar extract` shows only the examples that mention "extract".
- **Search everything**: `gamaxsene -s port` searches the examples of every command at once.
- **Grep-friendly**: `--oneline` prints `command  # description` on one line, and colors switch off automatically when output goes to a pipe or file.
- **Zero dependencies**: standard library only, Python 3.9+.
- **Easy to extend**: adding a command means adding one plain text file.

## Installation

You need Python 3.9+, [pipx](https://pipx.pypa.io) and git. On Ubuntu/Debian:

```bash
sudo apt install pipx git
pipx ensurepath        # then open a new terminal
```

Install straight from GitHub:

```bash
pipx install git+https://github.com/Merab25/Gamaxsene.git
```

pipx creates an isolated virtual environment for the tool and puts the `gamaxsene` command on your `PATH`.

```bash
pipx install git+https://github.com/Merab25/Gamaxsene.git@v0.1.0   # a specific release
pipx upgrade gamaxsene                                             # update
pipx uninstall gamaxsene                                           # remove
```

## Usage

| Command | What it does |
| --- | --- |
| `gamaxsene --help` | How the tool works, usage examples and all available commands |
| `gamaxsene find` | All examples for `find` |
| `gamaxsene find size` | Only `find` examples that mention "size" |
| `gamaxsene tar extract gz` | Several keywords: an example must match all of them |
| `gamaxsene -s port` | Search the examples of every command |
| `gamaxsene -l` | List commands with a summary and the number of examples |
| `gamaxsene grep -1` | One example per line: `command  # description` |
| `gamaxsene find --no-color` | Plain output (also `NO_COLOR=1`) |
| `gamaxsene -V` | Show the version |
| `python -m gamaxsene find` | Same as `gamaxsene find` |

Keywords are case-insensitive and match the **start of a word**: `port` finds "port", "ports" and `--port`, but not "export" or "report".

### Using it with grep

The built-in keyword filter covers most cases, but the output is designed to work with standard tools too:

```bash
gamaxsene find -1 | grep perm          # one line per example, grep sees command + description
gamaxsene find | grep -A1 -i "delete"  # match a description, also print the command below it
gamaxsene find | grep -B1 "exec"       # match a command, also print its description above it
gamaxsene -s docker -1 | less          # page through a search
gamaxsene curl json -1 > curl-json.sh  # save examples as a commented script
```

Exit codes make it usable in scripts: `0` when examples were printed, `1` for an unknown command or no matches.

## Available commands

### Files and directories

| Command | Examples | What it covers |
| --- | ---: | --- |
| `ls` | 32 | List directory contents with details, sorting and filtering |
| `cp` | 30 | Copy files and directories, with backups, preserving attributes |
| `find` | 37 | Search for files and directories by name, type, size, time and permissions |
| `du` | 30 | Show disk usage of files and directories |
| `chmod` | 30 | Change file and directory permissions |
| `tar` | 31 | Create, list and extract archives (.tar, .tar.gz, .tar.bz2, .tar.xz, .tar.zst) |

### Text processing

| Command | Examples | What it covers |
| --- | ---: | --- |
| `grep` | 32 | Search text for lines matching patterns |
| `sed` | 33 | Stream editor: find and replace, delete, insert and transform text |
| `awk` | 31 | Process text column by column: filter, sum, count and reformat |
| `sort` | 32 | Sort lines of text by alphabet, numbers, columns, versions and more |
| `xargs` | 30 | Build and run commands from standard input |
| `jq` | 35 | Query, filter and transform JSON on the command line |

### Processes and system

| Command | Examples | What it covers |
| --- | ---: | --- |
| `ps` | 32 | Show running processes with CPU, memory, owner and command |
| `lsof` | 30 | List open files, network sockets and the processes that use them |
| `systemctl` | 33 | Control systemd services, boot targets and timers |
| `journalctl` | 33 | Read and filter systemd journal logs |
| `crontab` | 32 | Schedule recurring jobs with cron (fields: minute hour day month weekday) |
| `apt` | 37 | Install, update and manage packages on Debian and Ubuntu |
| `date` | 33 | Show, format and calculate dates and times |
| `tmux` | 35 | Terminal multiplexer: sessions that survive disconnects, windows and panes |

### Networking

| Command | Examples | What it covers |
| --- | ---: | --- |
| `ip` | 32 | Show and manage network interfaces, IP addresses, routes and ARP |
| `ss` | 31 | Inspect network sockets and connections (modern netstat) |
| `dig` | 30 | DNS lookups: records, resolvers, propagation and debugging |
| `nc` | 30 | Netcat: test ports, send raw TCP/UDP data, move files (OpenBSD netcat) |
| `curl` | 35 | Transfer data with URLs: HTTP requests, REST APIs and downloads |
| `wget` | 31 | Non-interactive downloader: files, resumable downloads, website mirrors |
| `ssh` | 34 | Secure shell: remote login, remote commands, keys and tunnels |
| `rsync` | 31 | Fast incremental sync of files, locally or over SSH |
| `nmap` | 30 | Network scanner: hosts, ports, services (scan only networks you own or may test) |
| `tcpdump` | 32 | Capture and inspect network packets |
| `iptables` | 34 | Configure the Linux firewall (netfilter) for IPv4 |

### Security

| Command | Examples | What it covers |
| --- | ---: | --- |
| `openssl` | 34 | TLS certificates, keys, CSRs, hashing, random data and encryption |

### DevOps and cloud

| Command | Examples | What it covers |
| --- | ---: | --- |
| `git` | 44 | Version control: commits, branches, history, remotes and undo |
| `docker` | 42 | Build, run and manage containers, images, volumes and Compose stacks |
| `kubectl` | 42 | Manage Kubernetes clusters: pods, deployments, services, logs and rollouts |
| `terraform` | 38 | Infrastructure as code: plan, apply and manage cloud resources |
| `aws` | 38 | AWS CLI: S3, EC2, IAM, CloudWatch Logs, ECR, EKS and more |

Run `gamaxsene -l` for the live list.

## Example file format

Each command is one text file in [`src/gamaxsene/examples/`](src/gamaxsene/examples), named after the command (`find.txt`, `docker.txt`, ...):

```text
## Search for files and directories by name, type, size, time and permissions

# Find files by exact name in the current directory tree
find . -name "config.yaml"

# Web permissions: 755 for directories, 644 for files
find /var/www -type d -exec chmod 755 {} +
find /var/www -type f -exec chmod 644 {} +
```

- `## ...` on the first line is the one-line summary shown by `gamaxsene -l`.
- `# ...` starts a new example with its description.
- The following line(s) are the command. Several lines under one description belong to the same example.
- Blank lines are ignored.

## Adding a command

1. Create `src/gamaxsene/examples/<command>.txt` using the format above.
2. Aim for about 30 examples: the most common use first, then the important options, then advanced and combined usage.
3. Use realistic values (`/var/log/nginx/access.log`, `user@server`, `192.168.1.10`) instead of `<file>` placeholders, so examples can be copied and edited quickly.
4. Keep each command on one line.
5. Run the tests. They check that every file has a summary, at least 20 examples, and that every command is valid shell syntax (`bash -n`).

```bash
pytest
```

The new command shows up automatically in `--list`, `--help` and `--search`; no code changes are needed.

## Project structure

```text
gamaxsene/
├── .github/workflows/ci.yml   # CI: build, install the wheel, run tests on Python 3.9 / 3.12 / 3.13
├── src/gamaxsene/
│   ├── __init__.py            # package version (single source of truth)
│   ├── __main__.py            # enables `python -m gamaxsene`
│   ├── cli.py                 # argument parsing, file parsing, filtering and output
│   └── examples/              # one .txt file per command, shipped inside the package
├── tests/test_cli.py          # parser, example files and CLI behaviour tests
├── pyproject.toml             # package metadata, build backend, `gamaxsene` entry point
├── LICENSE
└── README.md
```

## How it works

- **Entry point**: `pyproject.toml` declares `gamaxsene = "gamaxsene.cli:main"` under `[project.scripts]`. When the package is installed, pip/pipx generate a small `gamaxsene` executable that calls `main()`.
- **Bundled data**: the example files live inside the package, so they are included in the wheel. At runtime `importlib.resources` finds them wherever the package was installed, instead of relying on hard-coded paths.
- **Parsing**: each file is read line by line into `Example(description, commands)` objects; filtering is a case-insensitive word-start match against the description and the commands.
- **Output**: colors are ANSI escape codes, enabled only when stdout is a terminal (`sys.stdout.isatty()`), so pipes, files and grep always get plain text.
- **Isolation**: pipx installs the tool in its own virtual environment, so it never conflicts with system Python packages.
- **Versioning**: the version is defined once in `src/gamaxsene/__init__.py` and read by the build backend (hatchling).

## Development

```bash
git clone https://github.com/Merab25/Gamaxsene.git
cd gamaxsene
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"    # editable install: code and example changes apply immediately

gamaxsene find             # try it
pytest                     # run the tests
python -m build            # build the wheel and sdist into dist/
```

To use your local copy as your everyday command, install it with pipx in editable mode:

```bash
pipx install -e . --force
```

## Roadmap

- Shell completion for bash and zsh
- Publish to PyPI (`pipx install gamaxsene`)
- More commands: `ufw`, `nginx`, `helm`, `ansible`, `strace`, `mount`, `useradd`
- Georgian descriptions

## Safety note

Some examples change or delete things (`rm`, `find -delete`, `iptables -F`, `docker system prune`, `terraform destroy`). Read a command before you run it. Only scan or capture traffic (`nmap`, `tcpdump`) on networks you own or have permission to test.

## License

[MIT](LICENSE)
