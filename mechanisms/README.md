# mechanisms

**Working machinery, not prose.** `lessons/` explains what went wrong and why; this directory
holds the things that stop it happening — hooks, scripts, skills, wrappers, automations —
in a form another agent can copy and run.

For *where* each kind of thing here actually lives — the machine copy vs. the repo copy, and
what (if anything) keeps them in sync — see
[`WHERE-MECHANISMS-LIVE.md`](WHERE-MECHANISMS-LIVE.md).

For *how many projects* a mechanism fires in — everything catalogued here is system-wide, and
repo-scoped guards were a class this corpus had no record of — plus how a machine declares which
mechanisms it wants and how a vendored copy is kept from diverging, see
[`SCOPE-AND-VENDORING.md`](SCOPE-AND-VENDORING.md).

Brad, 2026-07-22: *"I want every conductor to be able to write notes, process improvements,
mechanisms, hooks, skills, scripts, etc. into that repo, so every other conductor can benefit
on the next run."*

## Why this exists next to `lessons/`

A lesson is the **voluntary** class of control: it works only on an agent that read it,
remembered it, and chose to act on it. Every entry in `lessons/` is therefore one step weaker
than the mechanism it describes. `lessons/designing-the-problem-away.md` makes the argument in
full — the short version is that a rule an agent must recall at the right moment is the
intervention that already failed.

So: **when a lesson has a machine version, the machine version belongs here, and the lesson
should link to it.** A lesson with no mechanism is fine (some things genuinely cannot be
enforced), but it should say so rather than leave the reader assuming one exists.

## Ranking, from `lessons/designing-the-problem-away.md`

Prefer the top of this list. The single test is: **does it work on an agent that never read
any of this?**

| Class | Works on an unaware agent? | Example |
|---|---|---|
| **Structural** — the bad state cannot be represented | yes, the commit is rejected | a doc check that fails a build |
| **Instrumented** — the control lives in data you already read | yes | a log that states its own liveness, so "no events" cannot be read as "nothing happened" |
| **Interrupt** — fires without your participation | yes | a pacer that re-invokes you on a timer |
| **Guard-at-the-action** — blocks the call before it runs | yes | a PreToolUse hook rejecting a command shape that lies |
| **Voluntary** — requires remembering | **no, expect decay** | a note-capture script; every file in `lessons/` |

## What is here

| Path | What it does |
|---|---|
| `hooks/evidence_with_claim.py` | Stop hook. A negative-existence or verification claim must be accompanied by a span quoted **verbatim from a tool result in the same turn**; the hook checks the quote is really there. You cannot satisfy it without having run the check. Ships with its tests. |
| `hooks/pending_instructions.py` | SessionStart hook. Injects the human's outstanding instructions into context at turn 0, from every channel they use. Built after a run missed three explicit instructions that were sitting in a handoff file nothing required reading. |
| `hooks/hook_log.py` | Append-only record of hook fires. Records that a hook fired and on what — **never** a verdict on whether it was right; validity is computed separately. |
| `hooks/hook_rollup.py` | Reads that log and reports fires vs. overrides per hook, so a hook decaying into a nuisance is visible as data rather than as a hunch. |
| [`a-lease-so-two-agents-cannot-own-one-domain.md`](a-lease-so-two-agents-cannot-own-one-domain.md) | Stops two scheduled agents owning one domain at once, built after two ran a shared estate for a morning without detecting each other. A lease is **taken**, so occupancy is a running agent's default state rather than something inferred from what it happens to be doing — the check it replaces ("is a lock row open?") was true only while an agent was mid-write. Heartbeat expiry rather than a PID, because an agent has no stable OS process. Ships with the paired identity half (`%an` cannot distinguish an agent from its user when both commit through one `.gitconfig`), the asymmetry that stops that half generalising to an agent sharing a clone with its human, 24 mutation-verified tests, and an explicit list of what it **cannot** detect. |
| [`skills/freshness-check/`](skills/freshness-check/README.md) | Staleness registry for load-bearing doc claims nothing else watches — each entry carries `last_checked` + a cadence, swept by deterministic date math so no model decides what is stale. The skill alone is **Voluntary** and decayed exactly as the table predicts (19 seeded entries, zero sweeps in the weeks after), so it ships an **example** SessionStart trigger that moves the control to Instrumented, with the rejected Structural option and the trigger's blind spots both written down. |
| `template/status-page/` — **in the private [`conductor-bs`](https://github.com/bradjshannon/conductor-bs) repo** | Reference implementation of an operator↔agent status page as a mechanism stack: append-only jsonl channels with an explicit acknowledgement actor, a server that executes page code from `git show HEAD:` so uncommitted WIP cannot break the live page ("commit to publish" — Structural), stamped staleness on pinned cards (Instrumented), an evidence-or-UNVERIFIED gate on agent claims (Guard-at-the-action), and a stores-text-never-executes POST contract. Its `DESIGN.md` names the failure behind every rule; its data contract and a smoke-tested minimal generator are the starting point for standing one up elsewhere. Lives in the private repo because a running instance is wired to real machines; the design itself is portable. |

## This is a catalogue, not a runtime

**Nothing here is meant to execute from this repo.** These are installed **case by case, where
they earn their place** — copied into a machine's config, adapted, and wired to the event that
should fire them. Brad, 2026-07-22: *"the mechanisms don't necessarily have to work FROM the
repo — maybe they're installed case by case, as needed? whatever's most effective."*

That is deliberate, and it is the cheaper design:

- **A hook is only meaningful once wired to an event** in a specific harness. The wiring, not
  the file, is the mechanism — so the install step cannot be skipped anyway.
- **Machines differ.** Paths, usernames, repo layouts and which harness is in use all vary.
  A shared checkout pretending to be portable would break silently on the machine that did not
  write it, which is the failure mode this whole repo exists to document.
- **Not every mechanism suits every context.** A guard that pays for itself on an unattended
  overnight run is noise on an interactive one. Adoption should be a judgement, made per
  machine, with the option to decline.

**Which is why every machine keeps a report of what it actually has wired** — but that report
names a specific machine, so it is **machine-specific and lives in the private `conductor-bs`
repo, not here** (`installed/<HOST>.md`, generated by `conductor-bs`'s `tools/report-installed.py`).
Brad, 2026-07-22: *"every conductor should have a log stating what it's using, what it's not using,
how those things are implemented, and where its files live."* That log is exactly the kind of
computer-specific detail this public repo is not allowed to carry (see the boundary note below).

This directory is for the **generic, portable machinery itself** — a hook or wrapper another agent
can copy and adapt, naming nothing specific. Its *installation on a real box* — paths, wiring,
which harness, what was declined — is tactical and belongs in `conductor-bs`.

The corollary is the thing to watch: **an entry here is not in force anywhere.** Do not read the
presence of a file in this directory as evidence that the failure it addresses is handled on
your machine — check your own config for the wiring.

## Adopting one

These were written for a specific setup and are **not** drop-in portable. Before copying:

1. **Read the paths.** Several resolve repo locations or transcript directories for one
   machine. Grep for `Documents/GitHub`, `expanduser`, and hard-coded repo names.
2. **Wire it up.** A hook in a directory is inert — it needs an entry in the harness config
   naming the event it fires on. A mechanism that is present but unwired is the exact failure
   `lessons/` keeps documenting.
3. **Run its tests if it has them, and check they can fail.** Stub the core function to a
   constant and confirm the suite goes red before trusting a green one.

## Contributing

Same bar as `lessons/`: **one entry = one real failure**, dated, with the failure named. Plus
two extra requirements, because this directory holds code:

- **Say which class it lands in** (table above) and, if it is below Structural, what the
  higher-class version would have been and why it was rejected.
- **State what it cannot detect.** Every control here has a hole; the ones that hurt are the
  holes nobody wrote down. `evidence_with_claim` cannot tell a *relevant* quote from an
  irrelevant one — it proves a check was run, not that the check was the right one.
