# Table mode — design document

> Status: implemented in 0.6.0. Phases 1-8 of section 13 are all in, under
> `src/barem/table/`, with the module layout of section 11 and the tests of
> section 12 (fixtures, golden files per width, and the width invariant).
>
> Not done, because section 15 left them open on purpose: a sticky identity
> column, highlighting cells that changed between `--watch` refreshes,
> row-level alerting in the left margin, and a declarative profile format.
> Profiles for the headerless commands in section 9 (`du -sh *`, `last`) are
> also still missing — they have no header line to fingerprint, so they need
> `--no-header` and a different detection route.
>
> Two decisions differ from the text below, both because the original was
> wrong in a way the tests caught; each is noted at the relevant section.
>
> Target version: 0.3.0 (the project had already reached 0.5.0, so it shipped
> as 0.6.0)

## 1. What this is

Table mode turns the raw, hard-to-read output of standard Linux commands into a clean, readable table that adapts to the width of the terminal.

```bash
df -i | barem
ps aux | barem --sort %mem --top 10
ss -tlnp | barem
docker ps | barem
```

The tool reads the text from standard input, works out which command produced it, splits it into columns, decides what each column means (a size, a percentage, a status, a path), and prints it with alignment, colors and usage bars that match the meaning.

### Why it is worth building

- `df`, `ps`, `ss`, `lsblk` and `docker ps` print columns that do not line up once values get long, so the eye has to re-find each column on every row.
- The important number (a disk that is 95% full, a container that exited) looks exactly like every other number.
- Nothing in the output adapts to the terminal: on a narrow window lines wrap and the table falls apart.

Table mode fixes all three without replacing the commands. They stay the source of truth; this is only a nicer view of them.

### Design rules

1. **Readable before decorative.** Whitespace and alignment do most of the work. Lines and color only mark what matters.
2. **Never lie.** Shortened values are visibly marked (`…`), numbers are never truncated, and raw values stay available with `--raw`.
3. **Degrade cleanly.** No color, no Unicode, a narrow window or an unknown command must all still produce something useful.
4. **Zero dependencies.** Standard library only, like the rest of the project.

---

## 2. What the output looks like

### 2.1 Default style: clean, no heavy borders

The default has **no vertical lines and no box corners**. Columns are separated by two spaces, and a single light rule sits under the header. This is the layout that reads best and cannot break if a character width is miscalculated.

```text
$ df -h | barem

 FILESYSTEM       SIZE   USED   AVAIL  USE%               MOUNTED ON
 ──────────────────────────────────────────────────────────────────
 /dev/nvme0n1p2   468G   112G    332G  ▇▇▇░░░░░░░  25%    /
 /dev/sdb1        1.8T   1.7T     43G  ▇▇▇▇▇▇▇▇▇░  95%    /data
 /dev/nvme0n1p1   512M    62M    450M  ▇░░░░░░░░░  12%    /boot/efi
 tmpfs             16G   2.1M     16G  ░░░░░░░░░░   1%    /run

 4 filesystems · 2.3T total · 1.8T used (78%)
```

- Text columns are centred, numbers right-aligned, so the digits line up where the eye expects them.

> **Changed after review.** This section originally called for left-aligned
> text, and section 3 still lists `left` against the text kinds. Text, path and
> status columns are centred as built; numbers stay right-aligned, since
> centring them would undo the point of the column. The header is centred with
> its column so it still sits over its own values, and the Markdown export
> writes `:---:` for those columns.
- Headers are dimmed and uppercased so they recede behind the data.
- The summary line under the table is optional (`--no-summary`).

### 2.2 Boxed style (`--box`)

For people who prefer visible borders, or when pasting into a ticket:

```text
┌────────────────┬──────┬──────┬───────┬──────┬────────────┐
│ FILESYSTEM     │ SIZE │ USED │ AVAIL │ USE% │ MOUNTED ON │
├────────────────┼──────┼──────┼───────┼──────┼────────────┤
│ /dev/nvme0n1p2 │ 468G │ 112G │  332G │  25% │ /          │
│ /dev/sdb1      │ 1.8T │ 1.7T │   43G │  95% │ /data      │
└────────────────┴──────┴──────┴───────┴──────┴────────────┘
```

### 2.3 Other styles

| Style | Flag | Use for |
| --- | --- | --- |
| Clean (default) | — | Everyday terminal use |
| Boxed | `--box` | Screenshots, tickets, documentation |
| ASCII | `--ascii` | Old terminals, serial consoles, `ssh` into odd systems |
| Markdown | `--format md` | Pasting into GitHub, Jira, a README |
| CSV / TSV / JSON | `--format csv\|tsv\|json` | Feeding another script |
| Cards | automatic, or `--cards` | Terminals narrower than ~50 columns |

The ASCII style replaces the rule with `-`, the bar blocks with `#` and `.`, and `…` with `~`.

### 2.4 Card layout for narrow terminals

Below roughly 50 columns a table cannot work. Instead of wrapping into noise, each row becomes a small block:

```text
 /dev/sdb1
   Size      1.8T
   Used      1.7T
   Avail      43G
   Use%       95%  ▇▇▇▇▇▇▇▇▇░
   Mounted   /data

 tmpfs
   Size       16G
   Used      2.1M
   ...
```

The first column (the identifying one, marked in the profile) becomes the heading of each card.

---

## 3. Column model

Every column is described by this structure. Profiles fill it in; the generic parser guesses it.

```python
@dataclass
class Column:
    key: str  # stable id, e.g. "use_pct"
    header: str  # what is printed, e.g. "USE%"
    kind: Kind  # text | number | size | percent | status | path | time | duration
    align: Align  # left | right | center  (derived from kind by default)
    priority: int  # 1 = never drop, 5 = drop first
    min_width: int  # never shrink below this
    max_width: int | None  # never grow beyond this
    truncate: Trunc  # end | middle | none
    unit: str | None  # "B", "s", "%" ...
```

### Kinds and how each is rendered

| Kind | Alignment | Treatment |
| --- | --- | --- |
| `text` | left | Truncate at the end with `…` |
| `path` | left | Truncate in the **middle**: `/var/lib/…/overlay2` keeps the start and the file name |
| `number` | right | Thousands separators, never truncated |
| `size` | right | Humanized: `1.8T`, `512M`, `2.1M`; the unit letter is aligned in its own sub-column |
| `percent` | right | Number plus optional bar, colored by threshold (section 4) |
| `status` | left | Mapped to a color and an optional symbol (section 5) |
| `time` | right | Absolute (`09:14:22`) or relative (`3 min ago`) with `--relative` |
| `duration` | right | `2d 4h`, `18m`, `5.2s` |

Numbers are **never** truncated. If a numeric column cannot fit, the layout takes space from a text column instead, and only drops the numeric column as a last resort.

---

## 4. Percentages — the most important detail

Percentages carry the alert in most of these commands (`df` usage, `ps` CPU and memory), so they get the most care.

### 4.1 Layout

The cell is built from three fixed-width parts, so every row lines up perfectly:

```text
▇▇▇▇▇▇▇▇▇░  95%
│         │  │
│         │  └── number: right-aligned in 4 chars ("  1%" … "100%")
│         └───── one space
└─────────────── bar: fixed width, default 10 cells
```

- The bar width is fixed per table, not per row, so the numbers always start at the same column.
- `--bar-width N` changes it; `--bar-width 0` or `--no-bars` shows only the number.

> **As built, the number width is measured, not fixed at 4.** Four cells holds
> `  1%` to `100%`, but not `94.3%` from `ps`, nor `340%` from a multi-threaded
> process. Assuming 4 overflowed the table by exactly the difference, which the
> width invariant caught. The critical `!` also gets a column of its own rather
> than being appended, because `95%!` and ` 25%` otherwise have their digits one
> cell apart — the thing this section exists to prevent.
- The bar is dropped automatically when the terminal is narrow (it is the lowest-priority element inside the cell, see section 6).

### 4.2 Sub-cell precision

With 10 cells, one cell is 10%, which makes 94% and 99% look identical. Use the Unicode eighth blocks for the partial cell so the bar is accurate to about 1.25%:

```text
filled: █   partial: ▏ ▎ ▍ ▌ ▋ ▊ ▉   empty: ░
```

`95%` with 10 cells = 9 full blocks + a `▌` half block. In ASCII mode this falls back to `#` and `.` with no partial cell.

### 4.3 Thresholds and colors

| Range | Meaning | Color | ASCII marker |
| --- | --- | --- | --- |
| 0–69% | fine | green | none |
| 70–89% | watch | yellow | none |
| 90–100% | act now | red + bold | `!` after the number |

- Thresholds are configurable per column in a profile and globally with `--warn 80 --crit 95`, because 90% full is critical for a disk but normal for a CPU.
- Some columns are **inverted**: for "free" or "available" percentages, low is bad. The profile sets `invert: true`.
- Colors never carry meaning alone: the number is always printed, and critical rows also get `!` in ASCII mode and when `NO_COLOR` is set. This keeps the output usable for colorblind readers and in logs.
- Only the cell is colored, never the whole row. A colored row makes the other columns hard to read.

### 4.4 Values above 100%

`ps` reports more than 100% CPU for multi-threaded processes. The bar clamps at full and the number keeps the true value (`340%`), printed in a distinct color so it is clearly not a disk-style percentage.

---

## 5. Status columns

Known status words are mapped to a color and an optional symbol:

| Group | Words | Color | Symbol |
| --- | --- | --- | --- |
| good | `Up`, `Running`, `active`, `LISTEN`, `Ready`, `Completed`, `ESTAB` | green | `●` |
| busy | `Pending`, `ContainerCreating`, `Restarting`, `activating`, `SYN-SENT` | yellow | `◐` |
| bad | `Exited`, `Failed`, `Error`, `CrashLoopBackOff`, `inactive`, `dead` | red | `✖` |
| neutral | anything unknown | default | none |

Symbols appear only with `--symbols` (or always in `--ascii`, as `+`, `~`, `x`), so the default output stays calm.

---

## 6. Responsive layout algorithm

This is the core of the feature and the part worth explaining in an interview.

### 6.1 Deciding the available width

```python
width = (
    args.width  # explicit --width wins
    or int(os.environ.get("BAREM_WIDTH", 0))
    or shutil.get_terminal_size(fallback=(80, 24)).columns
)
width = max(width, 20)
width = min(width, args.max_width or 160)  # do not stretch across an ultrawide screen
```

When stdout is not a terminal (piped, redirected), `get_terminal_size` already falls back to 80, which is the right default for a file or another pipe.

### 6.2 Fitting the columns

1. **Measure.** For each column take the natural width = the widest of the header and all its rendered values (measured with the display-width function from section 7, not `len`).
2. **Fits?** If the sum plus the separators is within the budget, print it. Done.
3. **Shrink the flexible columns.** Columns with `kind` of `text` or `path`, taken from the lowest priority upward, lose width down to `min_width`. Space is removed from the widest flexible column first, so one very long path does not starve the rest.
4. **Drop cell extras.** Percentage bars are removed (highest `priority` number first), then status symbols. The numbers stay.
5. **Drop columns.** Starting from the highest `priority` number, drop whole columns. A dropped column is listed under the table: `hidden: inode, type (use --cols to force)`.
6. **Switch to cards.** If priority-1 columns alone still do not fit, or `width < 50`, render the card layout instead.

The column that identifies the row (`identity: true` in the profile, such as the filesystem or the container name) is never dropped and is the heading in card mode.

### 6.3 Truncation rules

- `text`: cut at the end, add `…` (`very long container nam…`).
- `path`: cut in the middle (`/var/lib/…/overlay2/diff`), keeping at least the first segment and the last segment, since both ends carry the meaning.
- `number`, `size`, `percent`, `duration`: never truncated; the layout takes the space elsewhere.
- Truncation happens on **grapheme boundaries**, never in the middle of a wide character or an ANSI sequence.

---

## 7. Correct widths, or the lines break

The single most common bug in hand-written table renderers. Three rules:

1. **Strip ANSI before measuring.** Color codes have zero display width. The renderer therefore measures the *plain* string and applies color only at the very last step, after padding.
2. **Handle wide characters.** CJK characters and many emoji occupy two cells. Use `unicodedata.east_asian_width(ch) in ("W", "F")` → width 2, combining marks (`unicodedata.combining(ch)`) → width 0, everything else → 1.
3. **Reject control characters.** Command output can contain `\t`, `\r` or escape sequences from a compromised file name. Tabs are expanded, other control characters are replaced with `·` before measuring, so nothing can shift the layout or inject escape codes into your terminal.

```python
def display_width(text: str) -> int:
    """Number of terminal cells a string occupies."""
```

This function is the foundation of the whole renderer, and its unit tests should be the first ones written.

---

## 8. Getting data in

### 8.1 Input formats detected automatically

| Format | Detection | Notes |
| --- | --- | --- |
| JSON array of objects | first non-space char is `[` or `{` | `docker inspect`, `aws --output json`, `ip -j` |
| JSON lines | every line parses as a JSON object | structured app logs |
| CSV / TSV | consistent separator count across lines | `--input csv` to force |
| `key=value` | most lines match `\w+=` | `/etc/os-release`, `env` |
| Columnar text | default | all classic Unix commands |

### 8.2 Parsing columnar text

The naive `line.split()` fails on real output, and the failures are worth knowing:

- `df` has a header `Mounted on` containing a space.
- `ls -l` has a date with spaces, and a file name that may also contain spaces.
- `ps aux` has a `COMMAND` column that contains the whole command line with its spaces.
- Numeric columns are **right-aligned**, so the header text does not start where the data starts.
- Values can be empty, leaving a gap that a split collapses.

The parser therefore works by **column positions, not by splitting**:

1. Read the header line and find the start and end index of each header word group.
2. Scan the first N data rows to find which character positions are blank in **every** row. These are the real column separators.
3. Reconcile with the header positions: a right-aligned numeric column ends at the header's end position; a left-aligned one starts at its start position.
4. The last column takes the rest of the line, keeping its internal spaces.
5. If a known profile matches, its explicit column spec overrides all of this.

> **As built, steps 2 and 3 are replaced by assigning data runs to header
> regions.** Scanning for positions blank in every row, then reconciling with
> the header, turned out to be unfixable on `docker ps`: the space inside
> `Exited (137) 5 hours ago` is blank in every *other* row, so it looks exactly
> like a separator, and no gap-width rule separated that case from the single
> space between `Used` and `Avail` in `df`.
>
> What works is to let the header decide how many columns there are and where
> each begins, then assign every run of data to the column its **end** falls
> inside. All four pieces of `Exited (137) 5 hours ago` end inside the STATUS
> region, so they rejoin; `cache` ends inside NAMES and stays separate. Using
> the end of the run is what makes a right-aligned number wider than its own
> header (`168404` under `VSZ`) land in the right column.
>
> Multi-word headers are then found by two rules: a word pair some row's value
> runs straight through is one column (`CONTAINER ID`, `Mounted on`), and a word
> one space after its neighbour with no data under it at all is a continuation
> (`Mounted on` again, when every mount point happens to be short). The
> single-space condition is what stops a genuinely empty column — `docker ps`
> PORTS when nothing publishes a port — from being swallowed.

### 8.3 Which command produced this?

The pipe gives us bytes, not the command name. In order:

1. `--as df` — explicit, always wins.
2. **Header fingerprint.** A dictionary maps a set of header words to a profile: `{"filesystem", "size", "used", "avail"}` → `df`, `{"user", "pid", "%cpu", "%mem"}` → `ps aux`, `{"container id", "image", "status", "ports"}` → `docker ps`. This handles the realistic cases, because these headers are stable.
3. **Wrapper mode.** `barem run df -i` runs the command itself, so the name is known with certainty, and it is also how `--watch` works.
4. **Generic fallback.** No profile matched: column kinds are guessed from the data (all values match a size pattern → `size`; all end in `%` → `percent`; the header is `%cpu` → percent), which still produces a clean table.

The generic path must be good, because it is what runs on the commands nobody wrote a profile for.

---

## 9. Profiles

A profile is a small Python module in `src/barem/table/profiles/`, one per command:

```python
DF = Profile(
    name="df",
    fingerprint={"filesystem", "size", "used", "avail"},
    columns=[
        Column("filesystem", "FILESYSTEM", Kind.PATH, priority=1, identity=True, min_width=10),
        Column("size", "SIZE", Kind.SIZE, priority=2),
        Column("used", "USED", Kind.SIZE, priority=3),
        Column("avail", "AVAIL", Kind.SIZE, priority=2),
        Column("use_pct", "USE%", Kind.PERCENT, priority=1, warn=70, crit=90),
        Column("target", "MOUNTED ON", Kind.PATH, priority=1, min_width=8),
    ],
    summary=lambda rows: f"{len(rows)} filesystems · {total(rows)} total",
)
```

Users can add their own profiles in `~/.config/barem/profiles/`, matching how personal examples work.

### Profiles to write first

`df`, `ps aux`, `ss -tlnp`, `lsblk`, `free -h`, `ip -br a`, `docker ps`, `docker images`, `kubectl get pods`, `systemctl list-units`, `du -sh *`, `mount`, `last`, `netstat`.

---

## 10. Command-line interface

```text
usage: barem [--as NAME] [--sort COL] [--top N] [--cols LIST] [--where EXPR]
                 [--format STYLE] [--box|--ascii|--cards] [--width N] [--max-width N]
                 [--no-bars|--bar-width N] [--warn N] [--crit N] [--no-color]
                 [--no-summary] [--raw] [--watch SECONDS]
```

| Flag | Effect |
| --- | --- |
| `--as df` | Force a profile |
| `--sort use%` / `--sort -size` | Sort by a column; `-` for descending; sorts by real value, not by text |
| `--top 10` | First N rows after sorting |
| `--cols fs,use%,target` | Choose and order columns |
| `--where 'use% > 80'` | Filter rows; supports `> < >= <= == != ~` (regex) |
| `--format md\|csv\|tsv\|json` | Export instead of rendering |
| `--watch 2` | Re-run (wrapper mode) every 2 seconds, redrawing in place |
| `--raw` | Print the untouched input, for checking what was changed |

`--sort`, `--top` and `--where` are what turn it from a prettifier into a tool: `ps aux | barem --sort -%mem --top 10` replaces a long `awk` and `sort` pipeline.

---

## 11. Code layout

```text
src/barem/table/
├── __init__.py       # render(text, options) -> str, the single public entry point
├── width.py          # display_width, truncate_end, truncate_middle, sanitize
├── model.py          # Column, Kind, Align, Row, Table dataclasses
├── detect.py         # input format detection + profile fingerprinting
├── parse/
│   ├── columnar.py   # position-based parser for classic command output
│   ├── structured.py # json, jsonl, csv, tsv, key=value
│   └── infer.py      # guess column kinds when no profile matches
├── layout.py         # the fit / shrink / drop / cards algorithm
├── render.py         # clean, box, ascii, markdown, cards renderers
├── theme.py          # colors, thresholds, bar characters, NO_COLOR handling
├── humanize.py       # sizes, durations, relative times, thousands separators
└── profiles/         # df.py, ps.py, ss.py, docker.py, kubectl.py, ...
```

Each module is independently testable, and `width.py` has no dependency on anything else.

---

## 12. Testing

The feature is easy to get subtly wrong, so tests are specified up front.

1. **Fixtures, not live commands.** Save real output of each command into `tests/fixtures/df-h.txt` etc. Tests never run `df`, so they are deterministic and pass in CI on any machine.
2. **Golden files per width.** Render each fixture at widths 40, 60, 80 and 120 and compare against stored expected output in `tests/golden/`. A layout regression shows up as a readable diff. `pytest --update-golden` regenerates them after an intended change.
3. **Width invariant.** For every golden file: no line's `display_width` exceeds the target width. This single assertion catches most layout bugs.
4. **Alignment invariant.** In the clean style, every row's column start positions are identical.
5. **Parser round-trip.** Every value in the fixture appears in the parsed table (nothing silently lost), and no cell contains a leftover separator.
6. **Hostile input:** names with spaces, UTF-8 and CJK characters, embedded ANSI codes, a 4000-character path, empty input, a header with no rows, ragged lines, 50,000 rows.
7. **Property test** (optional): random tables, random widths, assert that the output never exceeds the width and never drops a priority-1 column unless cards mode was chosen.

---

## 13. Implementation order

Each phase is useful on its own and can be committed and demonstrated separately.

| Phase | Content | Done when |
| --- | --- | --- |
| 1 | `width.py` + `model.py` + the clean renderer with fixed columns | A hard-coded table prints with correct alignment at any width |
| 2 | Columnar parser + kind inference | `df -h \| barem` works with no profile |
| 3 | Responsive layout: shrink, truncate, drop, cards | Resizing the terminal to 40 columns still gives readable output |
| 4 | `theme.py`: colors, thresholds, percentage bars, sizes | `df` and `ps` look like the examples in section 2 |
| 5 | Profiles for `df`, `ps`, `ss`, `docker ps` + fingerprint detection | Correct column kinds without `--as` |
| 6 | `--sort`, `--top`, `--where`, `--cols` | `ps aux \| barem --sort -%mem --top 10` |
| 7 | Structured input (json, csv), `--format md\|csv\|json` | `docker inspect \| barem` |
| 8 | Wrapper mode `barem run`, `--watch`, user profiles | `barem run --watch 2 df -h` |

---

## 14. Decisions and trade-offs

- **No `rich`, no `tabulate`.** Either library would do this in a fraction of the code, but the project's "zero dependencies" promise is part of what makes it easy to install anywhere, and writing the layout engine is the part with real engineering content.
- **Clean style, not boxes, by default.** Vertical borders add visual noise on every row and break the moment a character width is miscalculated. Alignment and whitespace carry the structure; the boxed style stays available for people who want it.
- **Color is secondary information.** The output must be exactly as understandable in a log file, in `NO_COLOR` mode, and for a colorblind reader.
- **Never modify data, only presentation.** Sorting and filtering change which rows are shown, never the values. `--raw` always gives back the original.
- **Fail soft.** If parsing fails for any reason, print the original input unchanged with a short note on stderr. A formatting tool must never be the reason an admin cannot read their disk usage.

---

## 15. Open questions

1. Should the identity column be sticky on the left when the table is wider than the screen and the user scrolls, or is dropping columns always the better answer?
2. For `--watch`, is a full redraw enough, or is it worth highlighting cells that changed since the previous refresh?
3. Should row-level alerting exist (a subtle marker in the left margin when any cell in the row is critical), or is cell color enough?
4. Should profiles eventually move to a declarative text format so that non-Python users can add them?
