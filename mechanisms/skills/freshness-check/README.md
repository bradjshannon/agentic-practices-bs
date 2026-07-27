# freshness-check — a staleness registry for claims nothing else watches

**Class: Voluntary** (see the ranking in [`../../README.md`](../../README.md)) — which is the
whole problem, and why this directory also ships an [example trigger](#the-example-trigger).

## What it is

Documentation makes assertions that quietly rot: a file path that will be moved, a version pin
that will be bumped, a port that will change, a model roster that ships a new entry, a "these
two files must match" rule. None of those errors announce themselves. The doc keeps reading
fine while being wrong, and a cold agent primed on it acts on the wrong thing.

A freshness registry is a small YAML list of those assertions, each with the date it was last
verified and how often it needs re-verifying. `check_freshness.py` does the date arithmetic and
prints what is due. The arithmetic is deterministic — **no model decides whether something is
stale**; a model is only handed the `how_to_check` instruction for entries the arithmetic
already flagged. That split is the point: the part that can hallucinate never decides.

Contents of this directory:

| File | What it is |
|---|---|
| `SKILL.md` | The skill's front matter + operating instructions. Was byte-identical to the deployed original; now carries one documentation-only correction (see [Divergence from the deployed copy](#divergence-from-the-deployed-copy)). |
| `check_freshness.py` | The engine. Pure date math + reporting; optional `--run` for mechanical checks. |
| `example-trigger/session_start_freshness.py` | **An example, not an install.** A SessionStart hook that surfaces overdue entries at turn 0. |

## Install

The engine is a Claude Code *skill*, so it installs by copying the directory into the skills
path — there is no package to install and nothing to build:

```sh
mkdir -p ~/.claude/skills/freshness-check
cp SKILL.md check_freshness.py ~/.claude/skills/freshness-check/
pip install pyyaml          # the only dependency
```

Project-scoped instead of user-scoped? Put the same two files in `<repo>/.claude/skills/`.
Not using Claude Code at all? The script is a standalone CLI — `SKILL.md` is just documentation
with front matter, and `python check_freshness.py path/to/freshness.md` works on its own.

Confirm it can actually report something before you trust it:

```sh
python check_freshness.py freshness.md --today 2099-01-01
```

On the day you seed a registry every entry reads OK, so a clean run proves nothing whatsoever.
Forcing a future date is the only way to find out whether your entries and `check_cmd`s work.
Do this. It is how the two `check_cmd` bugs recorded in `SKILL.md` were found.

## Starting a registry in a new project

1. Create `freshness.md` at the repo root with a short preamble and one fenced ` ```yaml ` block.
2. **Seed it from the docs a cold agent is primed on** — the entry-point files (`README.md`,
   `CLAUDE.md`/`AGENTS.md`, a contributing guide). Those are the claims that get acted on
   without being re-checked, so they are the ones worth a cadence.
3. Apply the scope rule below before adding anything.
4. Run with a future `--today` and fix what does not work.
5. Wire a trigger, or accept that it will not be swept. See [the example](#the-example-trigger).

**Scope discipline.** Register a claim only if it (a) will decay, (b) is load-bearing if wrong,
and (c) **is not already watched by a machine**. Do not register what your CI, your pre-commit
hooks, or your dependency bot already enforce — duplicating a machine check is noise, and a
noisy registry gets abandoned, which costs you the entries that mattered. Equally: delete
entries that stop being load-bearing. A registry that only accretes becomes the stale thing it
was built to catch.

**Organise by the file that owns the claim, not alphabetically by id.** Group entries under a
`# ===== path/to/file.md =====` comment divider. When that file moves to another repo, its
entries are a contiguous block you can cut and paste with it.

## The entry schema — as the parser actually reads it

Derived by reading `check_freshness.py` and three real registries, not from prose. The
distinction between the two "required" columns is real and worth knowing:

| Field | Required by the tool | Required by convention | What it is |
|---|---|---|---|
| `last_checked` | **yes** | yes | `YYYY-MM-DD`. Missing/unparseable ⇒ status `MALFORMED`. |
| `check_every_days` | **yes** | yes | Integer cadence. Missing/non-integer ⇒ `MALFORMED`. `<= 0` means status `ALWAYS` (check every sweep). |
| `id` | no (defaults to `?`) | yes | Stable slug. Without one the report cannot tell you *which* entry. |
| `claim` | no | yes | The volatile assertion, one line. Printed if present. |
| `location` | no | yes | Where the claim is relied on, as `file :: section`. Printed if present. |
| `how_to_check` | no | strongly | The verification instruction handed back to the agent. An entry without one is a staleness alarm with no attached action. |
| `trigger` | no | no | The real-world event that should force a check ahead of the numeric backstop. Printed, never evaluated — a human or agent has to notice it. |
| `check_cmd` | no | no | Shell one-liner run by `--run` on due entries. Read the warnings below. |
| `confidence` | no | no | Free text; flags an assumption vs. a verified fact. |

Status bands: `OK` (< cadence) · `DUE` (≥ cadence) · `OVERDUE` (≥ 2× cadence) · `ALWAYS`
(cadence ≤ 0) · `MALFORMED`. Exit codes: `0` nothing due · `1` something due/overdue/malformed
· `2` usage or parse error. The non-zero exit is what lets a hook, a checklist or a CI step
gate on staleness.

**File format.** A `.md`/`.markdown` file: *every* fenced ` ```yaml ` / ` ```yml ` block is
extracted and concatenated. Any other extension: the whole file is parsed as YAML. Either way
the result must be a list of entries, or a dict with an `entries:` list.

### `check_cmd`, and the three ways it lies

`--run` is the difference between a registry that reminds you to check and one that checks.
It is also where every bug so far has been. All three of these produce a *confident wrong
verdict*, which is worse than no check at all, because it is indistinguishable from a real hit.

1. **Relative paths resolve against the registry's own directory**, not the caller's cwd.
   That is deliberate — it is what lets a per-repo registry be plucked out and moved with its
   files. Write relative paths; do not "fix" them to absolute ones.
2. **POSIX shell *syntax* is refused on Windows, not run.** `--run` uses `shell=True`, which on
   Windows is `cmd.exe`, where `$(…)`, `${…}`, backticks, `&&`, `||` and `;` are not expanded.
   A version-comparison using `[ "$(grep …)" = "$(grep …)" ]` returned non-zero for two files
   that genuinely matched. The engine now refuses such a command with an explanation.
3. **POSIX *commands* are not refused — and on Windows they are a PATH lottery.** The refusal in
   (2) screens for shell metacharacters only. A `check_cmd` of `test -f a -a -f b`, or
   `grep -q x file`, contains none of them, so on Windows it runs. Whether it *works* depends
   entirely on the PATH of whatever process invoked the sweeper, because `--run` uses
   `subprocess.run(cmd, shell=True)` with **no `env=`** — the environment is inherited verbatim,
   and `cmd.exe` has no builtin `test`/`grep`, so resolution is pure PATH lookup for
   `test.exe`/`grep.exe`.

   Measured on one Windows box, 2026-07-27, same commands, same script, two shells:

   | Invoked from | `test -f README.md` | Why |
   |---|---|---|
   | Git Bash | `rc=0`, works | its PATH prepends `C:\Program Files\Git\usr\bin`, which ships `test.exe`, `grep.exe` |
   | PowerShell / `cmd.exe` | `rc=1`, *"'test' is not recognized…"* | the *system* PATH carries only `Git\cmd` and `Git\mingw64\bin`; neither holds `test.exe`. (A `C:\msys64\usr\bin` entry was on PATH and did **not** help — that install had no `test.exe`/`grep.exe`.) |

   So the failure is **conditional, not universal**, and the condition is one you cannot see from
   the registry: a `--run` sweep launched from a POSIX-ish shell passes, the identical sweep
   launched from PowerShell reports the entry STALE when nothing is wrong. That is worse than a
   flat failure — it is a check whose verdict depends on who started it. An earlier version of
   this file stated the hole as unconditional; it is not.

   **The guidance is unchanged, and the conditionality is the reason for it:** prefer a
   `check_cmd` that invokes a real cross-platform executable — `python tools/whatever.py <mode>`
   — and put anything shell-shaped into `how_to_check` prose. Across the three registries seeded
   so far, 17 of the 19 `check_cmd` entries are POSIX-shaped, so every one of them is
   PATH-dependent on Windows.

## Sweeper vs. project-specific checker — which piece are you getting?

Two different things, and adopting one is not adopting the other:

- **The sweeper** (this directory) is *generic and portable*. It knows about dates, cadences and
  statuses. It knows nothing about your project and never will.
- **A project-specific checker** — the pattern seen in the wild is a `tools/check_freshness_claims.py`
  inside a project repo, invoked from a `check_cmd` as `python tools/check_freshness_claims.py <mode>` —
  is the *domain half*. It holds the assertions that are too structural for a one-line shell
  test: "these two version fields in different files must match", "these seven status files must
  classify exactly this way, including the four that are supposed to still be open".

The split exists for three reasons, all of them earned:

- Some claims cannot be expressed as a shell one-liner at all, and a claim with no mechanical
  check degrades to prose that nobody re-runs.
- A cross-platform executable dodges hole (3) above outright.
- A real checker can **refuse to pass vacuously**. A glob that matched nothing, or a file that
  moved, must fail — not report "all clear". A shell `test` cannot tell you the difference
  between "the assertion held" and "I examined nothing"; a purpose-built checker can, and can
  print the scope it actually looked at so a vacuous pass is visible.

Adopting this directory gives you the sweeper. The domain checker is yours to write, one mode
at a time, as entries prove they need one.

## The example trigger

> **`example-trigger/` is an example to adapt. It is not installed anywhere, and it is not
> intended to be dropped into a live config unread.**

### The problem it answers

Everything above is the **Voluntary** class: it works only if somebody remembers to run it.
The ranking this repo uses says a rule that fails twice should move *up* a class rather than be
reworded. The observed failure: three registries, 19 entries, all seeded on one day, none swept
in the weeks after. Not defiance — nobody was ever prompted.

### What was considered, and the honest tradeoffs

| Option | Class | Why not chosen |
|---|---|---|
| Pre-commit hook failing on an overdue entry | Structural | The strongest on paper and rejected on purpose. Staleness is not caused by the commit it would block, and usually *cannot be resolved in the moment* — re-verifying a claim can mean a web search or a hardware check. So it blocks unrelated work for a reason the author cannot act on, which is the precise recipe for `--no-verify`. A gate that is routinely bypassed enforces nothing and also teaches the bypass habit to every other gate in the repo. |
| Scheduled task reporting overdue entries | Interrupt | Fires with no participation, which is genuinely better. But it needs a *sink* — a place the report lands where someone will see it — and if that sink is a file or an email nobody reads, it is Voluntary again with extra machinery. Adopt this one if you already have a working operator-notification channel. |
| Wind-down / handoff checklist step | Voluntary | The status quo. Named here only so it is not mistaken for a fix: it is the class that already failed. |
| **SessionStart hook injecting overdue entries as context** | **Instrumented** | **Chosen.** |

### Why the chosen one

The control lives in **data the agent already reads** — the opening context of the session. It
therefore works on an agent that has never read this repo, never heard of the registry, and has
no instruction to sweep anything: the overdue list is simply *there*, next to the claim it
contradicts, at the moment the agent is being primed on the document that carries it. It costs
nothing when clean (no output at all), needs no notification channel, and fires on an event
that already happens every single session.

It is deliberately one class below Structural. That is a trade of enforcement strength for a
much lower false-positive rate, made on the argument that the Structural version's false
positives would get it disabled.

### What it does not catch

- **It surfaces; it does not enforce.** An agent can read the block and do nothing. Nothing
  fails, nothing blocks. This is the honest ceiling of the Instrumented class.
- **No session, no notice.** A repo nobody opens for a month is swept zero times in that month,
  and it is exactly the neglected repo whose claims have rotted furthest.
- **It competes for attention at turn 0**, against priming, briefs and instructions. A long
  overdue list is *more* skippable than a short one — hence the line cap, and hence the scope
  rule that keeps registries small.
- **It is silent when broken.** Every failure path exits 0 and prints nothing, so a missing
  sweeper, an absent PyYAML, or a wrong path removes the control without telling anyone. That
  is chosen (a hook that can break session startup gets deleted after one bad morning), but it
  means *presence of the file is not evidence the control is live*. Run it by hand once, see it
  produce JSON, and only then believe it.
- **It only knows about registries it is told about**, via `FRESHNESS_REGISTRIES` or a
  `freshness.md` in the cwd. A new project's registry is invisible until someone adds it — the
  one voluntary step this design does not remove.

Install instructions and the environment variables are in the module docstring.

## Divergence from the deployed copy

The default is **byte-for-byte identical to the deployed original**, and it is a deliberate
default: a "portable" copy that quietly diverges from the copy actually running on a machine is
the drift this repo exists to document — a fix applied here never reaches the box, a fix applied
there never reaches anyone else. Fix it in one place and re-sync both. If you re-sync, note the
date here.

`check_freshness.py` is still byte-identical, including hole (3) above, which is left unfixed on
purpose (it is a documentation problem more than a code one — the conditionality is the point).

`SKILL.md` **has one intentional divergence**, 2026-07-27: its Registry-format section (and the
front matter) said the parser reads *one* fenced yaml block. That was true of an earlier
`re.search` implementation and is not true of the shipped script, which uses `re.findall` over
every fence. Corrected here only — the deployed copy under `~/.claude/` is the user's live setup
and is not edited from this repo. **Re-sync it when you next touch that setup**; until then the
deployed `SKILL.md` understates what its own engine does.

Copied 2026-07-27.
