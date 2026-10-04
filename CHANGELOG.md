# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the version
numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-10-04

### Added

- **Table mode.** Piping a command into `gamaxsene` now formats its output as a
  readable table that adapts to the terminal width, instead of looking anything
  up: `df -h | gamaxsene`, `ps aux | gamaxsene --sort -%mem --top 10`. The
  design is written up in [table-mode.md](table-mode.md) and implemented under
  `src/gamaxsene/table/`.
  - Columns are found by character position, not by `split()`, which real
    output defeats: `df` has a `Mounted on` header, `ps aux` keeps a whole
    command line in one column, `docker ps` has both plus a STATUS column
    reading `Exited (137) 5 hours ago`.
  - Column meanings — size, percentage, status, path, duration — drive
    alignment, humanizing and sorting, so `1.8T` sorts above `512M` rather
    than below it alphabetically.
  - Percentages get a usage bar accurate to about an eighth of a cell, with
    thresholds that colour the number and mark it `!` whenever colour is off.
  - The layout gives things up in order as the window narrows: text columns
    shrink, then bars and status symbols go, then whole columns are dropped
    and listed under the table, and below ~50 columns each row becomes a card.
    The identity column is never dropped and numbers are never truncated.
  - 18 profiles recognised by header fingerprint (`df`, `df -i`, `lsblk`,
    `lsblk -f`, `findmnt`, `ps aux`, `ps -ef`, `free`, `ss`, `netstat`,
    `ip -br a`, `docker ps`, `docker images`, `kubectl get pods`,
    `kubectl get nodes`, `systemctl list-units`, `list-unit-files`,
    `list-timers`), plus inference for everything else.
  - JSON, JSON lines, CSV, TSV and `key=value` input detected automatically.
  - `--sort`, `--top`, `--where`, `--cols`, `--format md|csv|tsv|json`,
    `--box`, `--ascii`, `--cards`, `--width`, `--bar-width`, `--warn`,
    `--crit`, `--symbols`, `--relative`, `--input`, `--raw`, `--profiles`.
  - `gamaxsene run df -h` runs the command itself, so its name is known for
    certain rather than guessed, and `--watch 2` re-runs and redraws in place.
  - User profiles load from `~/.config/gamaxsene/profiles/`.
- Tests for table mode: unit tests for the width functions first, parser tests
  for each way `split()` fails, the width and alignment invariants across every
  fixture, style and width, hostile input (embedded ANSI, CJK, a 4000-character
  path, 5,000 rows), and golden files per width regenerated with
  `pytest --update-golden`. 817 tests in total, up from 348.

### Changed

- The example lookup is unaffected: a command name always means examples, so
  table mode starts only when standard input is a pipe or a table flag says so.
- `ps` reports VSZ and RSS in kilobytes, so they render as plain numbers rather
  than being humanized as bytes, which would have understated them 1024x.
- `--warn` and `--crit` on the command line now override a profile's per-column
  thresholds, which previously won.

## [0.5.0] - 2026-10-01

### Added

- 40 more commands, taking the tool from 117 to **157 commands** and from
  3,918 to **5,314 examples**.
  - Core utilities: `dd`, `printf`, `seq`, `shuf`, `split`, `nl`, `comm`,
    `join`, `iconv`, `strings`, `xxd`, `sysctl`
  - Disks and filesystems: `fdisk`, `parted`, `mkfs`, `fsck`, `blkid`, `ncdu`,
    `smartctl`, `chattr`
  - Processes and system: `lsmod`, `lscpu`, `hostnamectl`, `timedatectl`,
    `at`, `sar`
  - Networking: `nft`, `nmcli`, `socat`, `mtr`, `sftp`, `netstat`, `whois`
  - Security: `firewall-cmd`, `setfacl`, `fail2ban-client`
  - Containers and cloud: `podman`, `gcloud`
  - Databases: `sqlite3`
  - Archives: `xz`
- A new **Disks and filesystems** README section, which `lsblk` moves into
  alongside the new partitioning, filesystem and health tools.

### Changed

- `dd` and `sysctl` were the two largest remaining gaps: fundamental tools
  that nothing else in the set substituted for.
- Every firewall front end is now covered in one place: `ufw` for Debian and
  Ubuntu, `firewall-cmd` for the RHEL family, `nft` for the layer underneath
  both, and `iptables` for the legacy syntax.

## [0.4.0] - 2026-10-01

### Added

- 40 more commands, chosen for everyday work rather than completeness, taking
  the tool from 77 to **117 commands** and from 2,540 to **3,918 examples**.
  - Files and directories: `touch`, `chown`, `file`, `tree`, `realpath`
  - Text processing: `cat`, `less`, `column`, `paste`, `rg`, `yq`, `base64`
  - Processes and system: `htop`, `nohup`, `nice`, `screen`, `vmstat`,
    `iostat`, `lsblk`, `logrotate`
  - Shell and environment: `echo`, `env`, `which`, `time`, `timeout`
  - Users and permissions: `id`
  - Packages: `dpkg`, `dnf`, `snap`
  - Editors: `vim`, `nano`
  - Languages and package tools: `python`, `pip`, `npm`
  - Databases: `psql`, `mysql`, `redis-cli`
  - Security: `gpg`, `sha256sum`, `certbot`
- Five new README sections: **Shell and environment**, **Packages**,
  **Editors**, **Languages and package tools** and **Databases**.

### Changed

- `chown` closes an odd gap: `chmod` was covered from the first release but
  changing ownership was not, although the two are used together constantly.
- `apt` moved from *Processes and system* into the new *Packages* section,
  next to `dpkg`, `dnf` and `snap`.

## [0.3.0] - 2026-09-30

### Added

- 40 more commands, taking the tool from 37 to **77 commands** and from 1,236
  to **2,540 examples**. Every command the previous roadmap named is now
  covered (`ufw`, `nginx`, `helm`, `ansible`, `strace`, `mount`, `useradd`).
  - Files and directories: `mv`, `rm`, `ln`, `mkdir`, `stat`, `df`
  - Text processing: `cut`, `tr`, `head`, `tail`, `wc`, `uniq`, `diff`, `tee`
  - Archives and compression: `zip`, `unzip`, `gzip`
  - Processes and system: `kill`, `pkill`, `top`, `watch`, `free`, `uname`,
    `dmesg`, `mount`, `strace`
  - Users and permissions: `useradd`, `passwd`, `sudo`
  - Networking: `ping`, `traceroute`, `host`, `scp`
  - Security: `ufw`, `ssh-keygen`
  - DevOps: `nginx`, `ansible`, `helm`, `make`, `gh`
- Two new README sections, **Archives and compression** and **Users and
  permissions**, for the groups that did not fit the existing ones.

### Fixed

- The README table check only recognised command names made of letters, so
  `ssh-keygen` would have been reported as missing from the docs. It now
  accepts hyphens and digits.

## [0.2.0] - 2026-09-30

### Added

- Tab completion for bash and zsh. `gamaxsene --completion bash` (or `zsh`)
  prints a script to install; TAB then completes command names, keywords and
  options. Candidates are read from the example files that are installed, so a
  command or keyword added later is completed without regenerating anything.
- `.gitattributes`, so the tree stays LF everywhere. The examples are shell
  commands read on Linux, and a wheel built from a Windows checkout would
  otherwise ship them with CRLF line endings.
- `.editorconfig` and a ruff configuration (lint and format), both enforced in
  CI alongside the tests.
- CI installs zsh and drives the generated bash completion function, so a
  broken completion script fails the build instead of silently offering nothing
  on a user's machine.
- A test that checks the README's command tables against the example files, so
  the counts and summaries in the docs cannot drift unnoticed.

### Fixed

- Every GitHub URL said `YOUR_USERNAME`, which left the CI badge blank and made
  the `pipx install` and `git clone` lines impossible to copy-paste.
- `README.md` carried its title twice.
- The test that runs `bash -n` over every example file piped the script in text
  mode, so on Windows Python rewrote the newlines as CRLF and bash failed with
  "unexpected end of file" on `date`, `dig` and `nc` rather than on any real
  syntax error. It now sends bytes.
- `completion_script()` walks one path segment at a time, because on Python 3.9
  a zipped package hands back a `zipfile.Path`, whose `joinpath()` took only a
  single argument at the time.

## [0.1.0] - 2026-09-30

### Added

- First release: the `gamaxsene` command, 37 Linux commands and 1,236
  copy-paste-ready examples.
- Keyword filtering (`gamaxsene find size`), search across every command
  (`gamaxsene -s port`), a command listing (`-l`) and grep-friendly one-line
  output (`-1`).
- Colors that switch off automatically when output is not a terminal, and
  exit codes that make the tool usable in scripts.
- Packaging with hatchling: the example files ship inside the wheel and are
  found with `importlib.resources`, wherever the package is installed.

[Unreleased]: https://github.com/Merab25/Gamaxsene/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/Merab25/Gamaxsene/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Merab25/Gamaxsene/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Merab25/Gamaxsene/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Merab25/Gamaxsene/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Merab25/Gamaxsene/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Merab25/Gamaxsene/releases/tag/v0.1.0
