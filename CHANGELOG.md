# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the version
numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.11.1] - 2026-10-05

### Fixed

- **Every link now names the repository as it is called today**, `Merab25/Barem`:
  the CI badge, the `pipx install` lines, the clone commands, the project URLs
  in `pyproject.toml`, the compare links here, and the `gh` and `pip` example
  files that use this repository as their example. GitHub's redirect had been
  hiding them.
- `.editorconfig` kept LF line endings for `src/gamaxsene/examples`, a path
  that has not existed since the package became `barem`, so the example files
  were not covered by the rule they exist for.

## [0.11.0] - 2026-10-05

### Changed

- **A percentage is drawn as upright pipes with nothing behind them**, twenty
  of them for 100%:

      |||||                  25%
      |||||||||||||||||||    95%!

  The shaded track the bars used to sit on was more ink than information, and
  the pipes still carry the colour that says how serious the number is. The
  old look is `--pct blocks`, the dotted track is `--pct ticks`, and
  `barem --styles` shows all eight.
- **A percentage that is not zero always draws at least one cell.** Rounding
  1% of twenty cells gives nothing, which reads as "unused" rather than
  "barely used"; one pipe says "a little" and the number beside it says how
  little.

## [0.10.0] - 2026-10-05

### Changed

- **The usage bar is 20 cells, twice as long as before**, so a percentage is
  readable at a glance rather than a smudge. The colour still carries the
  severity, and the blocks are still accurate to an eighth of a cell, which
  at this length puts the bar within half a percent of the number.
  `--bar-width N` sets another length, and `0` turns the bars off.
- **The bar length and the padding are now given up before any data is.**
  Twenty cells of bar and two spaces a side cost more room than an 80-column
  window has, so the layout tries every setting from the most generous down
  and keeps the one that concedes least: at 120 columns you get the full bar
  and the roomy cells, at 80 a shorter bar and tighter cells, and in both
  cases every column the window can hold. A column is dropped only once the
  decoration has nothing left to give.

### Performance

- The width measurements are kept while a table is being laid out, since the
  same columns are measured repeatedly as the layout backs off, and the cells
  are built once per bar length rather than once per attempt. Formatting 400
  rows of `ps aux` takes about as long as it did with one layout attempt.

## [0.9.0] - 2026-10-05

### Changed

- **The default look is `dashes-grid`**: a `+---+` frame with a rule between
  every row, so each row is a block you read across rather than a line in a
  wall of text. `--style box` restores the box-drawing frame, and the other
  seven styles are unchanged.
- **The table sits in the middle of the window.** `--left` puts it back
  against the margin, and card mode is always left-aligned because a centred
  list reads badly.
- **Column names are bold and bright, and the frame is dim.** They were both
  dim before, which made the names the palest thing on screen — the opposite
  of what a header is for. The row's own name stays bold too.
- **`--pad` defaults to 2**, for rows with room to breathe, and the padding is
  now the first thing the layout gives up: if two spaces a side would cost a
  column or the usage bars, the padding drops to one and the data stays. So a
  wide window gets the airy look and an 80-column one still shows everything.
- **A percentage in card mode is right-aligned**, so `1%`, `25%` and `95%!`
  line up down the card the way they do in a table column.

### Added

- **`--row-gap N`** puts N blank lines between rows, drawn so the frame is not
  broken by them, for a table you read across rather than down.
- **`--left`** turns the centring off.
- `barem --styles` now marks which border and percentage style is the default.

## [0.8.0] - 2026-10-05

### Added

- **Nine border styles and seven ways to draw a percentage**, chosen with
  `--style` and `--pct`. `barem --styles` renders the same table in all of
  them so you can pick by eye:

      barem --styles                 # the gallery
      df -h | barem --style grid     # a line between every row
      df -h | barem --pct dots       # ●●●○○○○○○  25%

  Borders: `box` (the default), `rounded`, `double`, `grid`, `dashes`,
  `dashes-grid`, `simple`, `clean`, `minimal`. Percentages: `blocks` (the
  default), `shade`, `bracket`, `dots`, `line`, `pipes`, `number`. Both are
  registries, so a new look is a dictionary entry rather than a change to the
  renderer, and each one has an ASCII twin that `--ascii` falls back to.
- **`--pad N`** sets the spacing inside every cell, either side (default 1).

### Changed

- **Nothing is cropped any more.** A value too wide for its column is wrapped
  onto as many lines as it needs instead of being cut with an `…`, breaking at
  spaces first and then after `/ , ; : = & |` so a path still reads as a path
  and `users:(("postgres",pid=1337,fd=7))` stays legible. `--no-wrap` restores
  the old behaviour.
- **The column that names the row keeps its full width** until the layout has
  run out of columns it could drop instead: giving up a column you can ask back
  with `--cols` beats wrapping every name across two lines. It is also
  emphasised, so the eye finds it first.
- **A percentage header sits over its number** rather than at the cell edge,
  so `USE%` is directly above `25%`.
- **More room around a percentage**: two spaces between the bar and the
  number, and the number, bar and critical marker are each a fixed width, so
  every row lines up whatever the values are.
- `ps` keeps at least eight cells for `USER`, so `postgres` and `www-data` are
  no longer split across two lines, and `STAT` keeps four so its header is not.

## [0.7.0] - 2026-10-05

### Changed

- **The tool is now called `barem`.** The command, the Python package, the
  completion scripts and the width environment variable (`BAREM_WIDTH`) all
  follow. The GitHub repository keeps its own name, so the install URL is
  unchanged — only `pipx install` puts a `barem` on your PATH instead.
  Upgrading in place therefore leaves the old command behind:
  `pipx uninstall gamaxsene` after installing the new one.
- **Tables are drawn with borders by default.** `--clean` gives the previous
  borderless layout, and `--ascii` now draws the same borders in `+---+` for a
  terminal that cannot manage the box-drawing characters.

### Added

- **`barem help`** runs the diagnostics you reach for first when something is
  off, and reports only what is actually wrong:

      barem help              # just the problems
      barem help --all        # every check, including the ones that passed

  Fifteen checks: disk space and inodes, memory and swap, load against the core
  count, failed systemd units, read-only filesystems, OOM kills, kernel I/O
  errors, the default route, DNS, clock synchronisation, a pending reboot,
  zombie processes and open file descriptors. Each one carries the command
  worth running next, and the worst three are printed under the table.

  The exit code is usable in a script: `0` clean, `1` warnings only, `2`
  something critical. `--format json` gives the whole result machine-readably.

  Every check is read-only, needs no root, and has a four-second timeout, so
  running it cannot make a bad situation worse and a hung mount cannot hang the
  diagnosis. A check whose command is missing reports `skipped`, which is what
  a container without `systemctl` gets.

  `barem check` and `barem doctor` are the same command. `barem --help` still
  prints the usage text — the diagnosis is the bare word, the usage is the flag.
- `table.render_table()`, so a table built in memory gets the same borders,
  widths, colours and responsive layout as piped output. `barem help` uses it.

### Fixed

- The `df` percent column is found by its header rather than by position,
  because `df -P` calls it Capacity and `df -Pi` calls it IUse%, and a fixed
  index misreads anything that is not GNU coreutils exactly.

## [0.6.1] - 2026-10-04

### Changed

- Text, path and status columns are centred, with their headers centred over
  them, and the Markdown export writes `:---:` for those columns. Numbers stay
  right-aligned so digits still line up. Section 2.1 of the design had called
  for left-aligned text; the note there records the change.

### Fixed

- `free -h` merged its first two columns, reading `Mem: 31Gi`. Its header is
  indented because the column holding `Mem:` and `Swap:` has no title, so that
  column now gets a slot of its own even though the header does not name it.
- `systemctl list-units` merged UNIT with LOAD. A unit name longer than the
  UNIT header ran across the gap to LOAD, and the rule that recognises
  `CONTAINER ID` as one column treated the two as one. Word pairs are only
  merged across a gap of one or two spaces now, which is what a two-word
  header actually has.
- Percentages and numbers keep the precision the command printed. `0.027%` was
  being shown as `0.0%`, which threw away the only information in the cell,
  and a column could mix `142.50` with `1,420`.
- `--no-header` input was printed unchanged instead of being formatted: with no
  header there were no column names, and a table with no columns fell through
  to the raw-output path. Such columns now render without a header row at all.

### Added

- **Table mode.** Piping a command into `barem` now formats its output as a
  readable table that adapts to the terminal width, instead of looking anything
  up: `df -h | barem`, `ps aux | barem --sort -%mem --top 10`. The
  design is written up in [table-mode.md](table-mode.md) and implemented under
  `src/barem/table/`.
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
  - `barem run df -h` runs the command itself, so its name is known for
    certain rather than guessed, and `--watch 2` re-runs and redraws in place.
  - User profiles load from `~/.config/barem/profiles/`.
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

- Tab completion for bash and zsh. `barem --completion bash` (or `zsh`)
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

- First release: the `barem` command, 37 Linux commands and 1,236
  copy-paste-ready examples.
- Keyword filtering (`barem find size`), search across every command
  (`barem -s port`), a command listing (`-l`) and grep-friendly one-line
  output (`-1`).
- Colors that switch off automatically when output is not a terminal, and
  exit codes that make the tool usable in scripts.
- Packaging with hatchling: the example files ship inside the wheel and are
  found with `importlib.resources`, wherever the package is installed.

[Unreleased]: https://github.com/Merab25/Barem/compare/v0.11.1...HEAD
[0.11.1]: https://github.com/Merab25/Barem/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/Merab25/Barem/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/Merab25/Barem/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/Merab25/Barem/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/Merab25/Barem/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Merab25/Barem/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/Merab25/Barem/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/Merab25/Barem/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Merab25/Barem/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Merab25/Barem/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Merab25/Barem/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Merab25/Barem/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Merab25/Barem/releases/tag/v0.1.0
