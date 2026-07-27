---
name: freshness-check
description: >
  Check a freshness/staleness registry for entries due for re-verification. Use whenever the user
  asks to "check freshness", "what's stale", "review the freshness registry", "what needs
  re-checking", "sweep staleness", or during a wind-down / handoff when volatile assertions
  (model rosters, pricing, API surfaces, external facts) should be reviewed on a cadence rather
  than by memory. Operates on any markdown file with one or more fenced yaml blocks of entries
  (default: freshness.md) or a plain .yaml registry.
---

# Freshness check

Reports which registry entries are **due for re-verification** based on their recorded
`last_checked` date and `check_every_days` cadence. The due-ness computation is deterministic
(a bundled script does pure date math — it cannot hallucinate a status); the actual verification
of each due entry is handed back to you as its `how_to_check` instruction.

## When to run

- On demand ("what's gone stale?").
- **During wind-down** — this is the enforced trigger. A quarantined roster block or a lone
  "current as of DATE" line makes updates *cheap* but nothing forces them; running this in the
  wind-down pass is what converts "someone should remember" into an actual gate. The non-zero
  exit code on any due entry lets you fail a wind-down checklist or CI step until the sweep is
  done.

## How to run

```
python3 check_freshness.py [path]            # default path: freshness.md in cwd
python3 check_freshness.py freshness.md --run    # also execute check_cmd for due entries
python3 check_freshness.py freshness.md --all    # include OK entries in output
python3 check_freshness.py freshness.md --today 2026-09-01   # test/preview a future date
```

Requires `pyyaml` (`pip install pyyaml`). Exit codes: `0` nothing due · `1` something due,
overdue, or malformed · `2` usage/parse error.

Status bands: **OK** (< cadence) · **DUE** (≥ cadence) · **OVERDUE** (≥ 2× cadence) ·
**ALWAYS** (cadence ≤ 0) · **MALFORMED** (missing/unparseable `last_checked` or
`check_every_days` — surfaced, never silently skipped).

## What to do with the output

For each DUE/OVERDUE entry: perform its `how_to_check` (usually a web search + compare to the
recorded `claim`), then either (a) the claim still holds → bump `last_checked` to today, or
(b) it changed → update the source doc named in `location` **and** the registry entry, then bump
`last_checked`. For an entry whose `trigger` event has fired (e.g. a model release), check it
regardless of whether the numeric cadence is up. `--run` executes an entry's `check_cmd` via the
shell for mechanical checks — it runs commands defined *in the registry file*, so only point this
at a registry you authored.

## Registry format

A markdown file holding a list of entries in one or more fenced ` ```yaml `/` ```yml ` blocks —
**every** fence is extracted and the blocks are concatenated, so a registry may split its entries
across several fences (or keep them in one with comment dividers; both work). Or a plain
`.yaml`/`.yml` file that is a list, or a dict with an `entries:` list. Per entry:

| field | required | purpose |
|---|---|---|
| `id` | yes | stable slug |
| `claim` | yes | the volatile assertion, one line |
| `location` | yes | where the claim is relied on (file :: section) |
| `last_checked` | yes | `YYYY-MM-DD`, last verified |
| `check_every_days` | yes | numeric cadence — the time backstop |
| `trigger` | no | the real-world event that should force a check before the backstop |
| `how_to_check` | no | verification instruction |
| `check_cmd` | no | shell one-liner for mechanical checks (`--run`) — see the rules below |
| `confidence` | no | flag assumptions vs verified facts |

### Writing a `check_cmd` — both rules learned the hard way, 2026-07-26

- **Relative paths are correct, and they resolve against the REGISTRY'S own directory**, not the
  caller's cwd. That is deliberate: it is what lets a per-repo registry be plucked out and moved
  with its files. Do not switch to absolute paths — they defeat the point. (7 of 19 seeded entries
  reported a false STALE before the runner was fixed to do this.)
- **No POSIX shell syntax on Windows.** `--run` uses `shell=True`, which there is `cmd.exe`, so
  `$(…)`, `${…}`, backticks and quoted `&&` are not expanded. A check comparing two version strings
  with `[ "$(grep …)" = "$(grep …)" ]` returned **non-zero for two files that genuinely matched** —
  cmd.exe compared the literal command text. The checker now **refuses** such a `check_cmd` with an
  explanation instead of running it, because a wrong verdict here is indistinguishable from a real
  staleness hit. Use a plain argv command, or move the comparison into `how_to_check` prose.

### Test a new entry with a FUTURE `--today`

On the day you seed a registry, every entry reads OK and `--run` never executes anything — so
"0 need attention" says nothing about whether your checks work. `--today 2026-09-15 --run` forces
them due and actually runs them. That is what exposed the cwd bug above.

## Scope discipline

Register only what (a) will decay, (b) is load-bearing if wrong, and (c) is not already watched
by a machine. Do not register dependency versions a bot tracks — that is noise, and a noisy
registry gets abandoned. Delete entries that stop being load-bearing: the registry must subtract
as well as accrete, or it becomes the stale thing it was meant to catch.
