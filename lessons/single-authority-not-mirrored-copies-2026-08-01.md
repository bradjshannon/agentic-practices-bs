# A fact restated in four files is wrong in three of them — 2026-08-01

## What happened

The operator asked, mid-run, why a rule he had changed hours earlier had not taken effect:

> *"conductor brief should state that wind-down soft-trigger is 50% context. why did that not get
> updated? is local routine/skill not automatically updated when plugin updates?"*

The brief **had** been updated. What had not were the three other files that also stated the number.
Measured:

| file | said | how it updates |
|---|---|---|
| `conductors/iotta/brief.md` (the authority) | **50%** | edited directly |
| `~/.claude/scheduled-tasks/<task>/SKILL.md` | 60% | **nothing syncs it** — no repo copy existed at all |
| `conductor-bs/skills/conductor-winddown/SKILL.md` | 60% | editable, but nobody did |
| the same skill's **plugin cache** copy | 70% | one-way, refreshed only on plugin *update* |

The figure had moved 85% → 70% → 60% → 50%. Each move updated the file the operator was looking at
and left the rest behind, so at every moment most copies were wrong and **nothing announced it**.
An agent priming for a run reads whichever copy it happens to open first.

## The wrong fix, which is the tempting one

Mirror the four files so they agree. **This does not work, and reasoning about why produces the
actual rule.** Mirroring makes copies *identical*, not *correct* — four synchronised wrong numbers
is not an improvement, and the moment the authority changes you are back to a propagation race. It
also cannot touch the plugin cache at all: no session can write there.

## The two failures are different and need different machines

1. **DRIFT** — one artifact exists in two places and the copies diverge. Fix: declare one side the
   source, mirror it, and check. This is what a sync tool is for.
2. **RESTATEMENT** — one *fact* is written into several artifacts. Fix: the fact appears **once**;
   everything else points at it. A sync tool cannot help.

Conflating them is why "keep things in sync" gets built as a copier and then fails to prevent
anything.

## The rule that falls out, and it generalises past config files

> **Anything that cannot be synced must not carry state.**

The plugin cache is unwritable and stale by construction — so the *fix for the cache* is to make the
cached file contain no facts. A file that carries only procedure, and points at an authority for
every figure, **cannot go stale**. That is a stronger property than being up to date, and it is
available in cases where being up to date is not.

## What was built

`conductor-sync.py`: mirror check with an **explicit direction** (`--apply repo` / `--apply
machine`, never inferred — both sides are legitimately hand-edited and a wrong guess silently
destroys whichever was newer), plus an authority lint that fails when a single-authority fact is
restated outside its home. Wired into prime and into the wind-down check.

The lint is deliberately narrow — it matches a percentage presented as *the instruction*, not every
percentage near the topic — and was controlled 9/9 before being trusted: 4 instruction phrasings
caught, quiet on the separate "hard ceiling" fact, on past-tense narrative, and on the sentences
documenting the rule itself. **A guard with false positives gets bypassed and takes its true
positives with it**, so the control mattered more than the coverage. On first run it immediately
found two more live instances in a sibling skill nobody had looked at.

## The second finding, which was the bigger one

Building the mirror list required inventorying what actually lived where. **789 lines of
machine-local conductor files — six SME agent definitions and the scheduled-task wrapper — existed
on one disk, in no repository.** The brief separately names the agent definition as *the only
durable carrier of SME learnings across runs*, because cross-session agent revival had been measured
impossible. So the artifact the system designated as durable was the one artifact not under version
control, and nobody noticed because the *designation* and the *storage* were decided in different
places.

**Worth generalising:** when a design names something as the durable/canonical carrier, check that
the claim is true of where it physically lives. "This is the source of truth" is a statement about
intent; version control is a statement about fact.
