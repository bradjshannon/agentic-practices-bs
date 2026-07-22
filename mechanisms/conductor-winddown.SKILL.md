---
name: conductor-winddown
description: End a conductor run so the NEXT one starts strong — extract judgment, cold-read for blind spots, prune priming, hand off in-flight work, schedule the successor. Use at ~85% context, when the run's work is done, or when Brad says wind down. Also use if a run is about to end for any reason (context, time, interruption) and the handoff has not been written.
---

# Conductor wind-down

## Why this exists

A conductor run is a **Prestige cycle** (Brad's framing, 2026-07-19): the next run resets to
zero context and carries over **only what is on disk**. Brief, project memory,
`docs/needs-you.md`, the dashboard, tools, hooks. Nothing else survives — the tool that
creates scheduled runs says so outright: *"Each run starts fresh with no memory of this
conversation."*

So the prestige bonus is exactly what the ending conductor chose to persist. And choosing
was **voluntary**, which is this system's known failure mode: an agent that builds
voluntary tools also does voluntary handoffs, and a run that ends badly — context gone,
interrupted, or simply tired — prestiges with a weak bonus that the next conductor pays
for by re-deriving everything.

## Precondition: wind-down is TERMINAL, not background

**Do not start wind-down while a subagent is still running.** "The run's work is done" means:
no subagent running, nothing unpushed, queue empty or human-blocked. Finishing your *own*
track while an agent works does **not** count.

Paid for by the workpc conductor, 2026-07-22: it entered wind-down at ~72% context with a
subagent still going and commissioned the cold read there. The cold read reviewed a
**truncated** session — it missed the only push to an auto-deploying branch and the entire
final phase — while *looking* like a complete review. It had to be deleted. A truncated
cold read is worse than none, because it is indistinguishable from a real one.

Corollary on the trigger: ~85% context is a *ceiling*, not a start gun. If agents are still
out at 85%, your options are to wait, or to bank their work (ask them to commit+push what
they have) and stop them deliberately — not to wind down over the top of them. And check
that your context math uses the real window: the same conductor wound down ~5x early by
computing against 200k when the model window was 1M.

**Worse, and confirmed 2026-07-19: transcripts do not survive.** `~/.claude/file-history`
spans three months while `~/.claude/projects` held *only that day's* transcripts — 64
files, all one date. Sessions from previous days had been deleted or rotated. **You cannot
assume anything you did not write to a durable file will be readable later.** The
transcript is not a record; it is a buffer.

## The split — three jobs, only one needs you

| job | who | why |
|---|---|---|
| **Judgment** — what matters, what's next, what you are unsure of | **YOU. Not delegable.** | It is not in the transcript in recoverable form. It is your read of the situation, and a subagent reading your tool calls cannot reconstruct it. This is the highest-value artifact of the entire run. |
| **Blind spots** — what you cannot see because you are inside it | a cold-read agent | Proven on 2026-07-19: a mining agent found that the conductor defaults to building *voluntary* tools — a pattern the conductor had lived all day and never articulated. |
| **Mechanical** — dashboard, backups, index regeneration, successor scheduling | scripts / subagents | No judgment required, so no judgment should be spent. |

Do them in that order. The judgment dump first, because if the run is cut short mid-wind-down,
that is the piece you cannot afford to lose.

## Step 1 — Judgment dump (YOU, first, before anything else)

Append a dated section to `iotta-firmware/docs/decisions.md` and refresh
`iotta-firmware/docs/needs-you.md`. Answer these, tersely, in your own voice:

1. **What did I learn that is not obvious from the commits?** The commits record *what*;
   this records *why it mattered* and *what it cost*.
2. **What is in flight, and exactly where did I leave it?** Branch, file, the next
   concrete action. Assume the reader has never seen it.
3. **What am I uncertain about?** Claims I made that I could not verify. Say which. A
   confident handoff of a shaky claim is how the queue accumulates false "already exists"
   entries.
4. **What would I tell my successor in one sentence if I could only say one thing?**
5. **What did I get wrong today, and what is the corrected version?** Corrections are
   worth more than findings — they stop the next run repeating the error.

**Every open question ships with (a) the assumption taken, (b) what was built on it, and
(c) what it costs to change if the answer differs.** Field (c) is what lets a late answer
redirect work without re-deriving anything.

## Step 2 — Cold read for blind spots (delegate, in parallel with step 3)

Launch a subagent to read this session's transcript
(`~/.claude/projects/<cwd-slug>/<session>.jsonl`) with **no context from you**. Brief it to
look for what neither of you knows to look for — not a summary, which is worthless, but:

- recurring shapes in the conductor's *own* errors (the "voluntary tools" finding came from exactly this);
- assertions made without checking, and whether they held;
- questions Brad asked that were answered thinly or not at all;
- work started and silently abandoned;
- anything the conductor said it would do and did not.

Require it to quote verbatim and to distinguish confirmed from inferred.

**Have it WRITE TO A FILE — `iotta-firmware/docs/cold-read-<date>.md` — and do NOT read
that file yourself** (Brad, 2026-07-20). Reading it invites defending or re-framing the
findings; the next conductor would then inherit your digest rather than the raw
observation. Instruct the agent to return only a one-line confirmation, and to write
**incrementally**, because the first attempt at this died before writing anything and left
a zero-byte file.

Verify the file **exists and is non-empty** — that check is legitimate and does not
contaminate anything. Then add it to priming (the brief's Prime step already points at
`cold-read-*.md`) and commit it. **Expect it to be unflattering; a flattering one is
evidence the mechanism failed.**

## Step 2b — Tooling-opportunity analysis (delegate; runs alongside the cold read)

The cold read asks *"what did this conductor get wrong?"* This asks the complementary question:
**"what should we BUILD so it cannot happen again?"** Run it here, every wind-down:

```
/tooling-opportunity                      # resolves this session automatically
```

(`iotta-firmware/tools/workflows/tooling-opportunity.workflow.js` — five lenses over a
deterministic transcript census, then synthesis, then an adversarial pass that attacks each
recommendation with the coupling question, then a schema'd emit into `docs/reviews/`.)

**Why it is invoked HERE rather than left to judgement.** Its author flagged the honest defect
in its own report: *"the workflow itself is Voluntary class — nothing forces it to run."* That
is the one class this whole system says decays. Wiring it into the wind-down is the cheapest
available upgrade — the wind-down already runs at the end of every run, so the workflow
inherits that trigger instead of needing to be remembered. Not structural, but it moves the
control off "the conductor thought of it."

**Do read this one** (unlike the cold read). Its output is recommendations for machinery you
are about to hand to your successor, not observations about you, so there is nothing for you to
defend and every reason to sanity-check it. Bank anything cross-machine into
`agentic-practices-bs` (see Prime step 0c) rather than leaving it in one project.

Its recommendations are graded against the enforcement-class table, and anything that reduces
to "remember to X" is surfaced under *Rejected — failed the enforcement bar* rather than
deleted. **Read that rejected section**: a recommendation that keeps reappearing there is a
real problem with no mechanism yet, which is exactly the thing worth your judgement.

## Step 3 — Prune the priming (YOU, judgment required)

The brief **accretes**. Every run adds lessons; nothing removes them; eventually priming
costs more than it returns. So each wind-down must also *subtract*:

- **Fold duplicates.** The same lesson stated three ways is one lesson and two distractions.
- **Delete what is now enforced by a machine.** Once a hook or check exists, the prose that
  described the rule is dead weight — point at the mechanism instead.
- **Cut anything the next conductor does not need to know *before starting work*.** Detail
  belongs to SME agents and to `docs/`, not to priming. Priming is for orientation and
  hazards, not knowledge.
- **Re-read the Prime section as if you had never seen it.** Is a repo missing? (`iotta-setup`
  was absent for four runs and cost a 1h40m undiagnosable deploy.) Is a step now wrong?

Also consider whether an **SME agent** (`~/.claude/agents/*.md`) should be created or
refined for work this run found repetitive — that is priming that does not cost the
conductor any context at all, which is the best kind.

## Step 3b — DUMP the run's practices and tooling, and LAND them (Brad, 2026-07-22)

Two dumps, both ending in **commit / merge / push**. A run's machinery is worth nothing to the
next conductor if it is sitting in a local config or an unpushed branch — and this is not
hypothetical: one run had **seven mechanisms unbacked-up for weeks** (including the pacer and
the only working context reading), a handoff file written but never read, and hooks that existed
only on one machine. Three carriers, all failing silently, in one session.

**A. `agentic-practices-bs` — the CROSS-MACHINE dump.**
The test is **not** "was it useful here." It is: **"would the next conductor, on the OTHER
machine, want this?"** If yes, it goes here — `~/.claude` and the per-host `dotfiles-bs` backup
are both invisible to the other box.

- `lessons/` — a failure this run paid for, in the repo's four-part shape (Symptom / What
  actually happened / The rule / Why it generalises). **One entry = one real failure.** If you
  cannot name the failure, it does not go in.
- `mechanisms/` — hooks, scripts, skills, wrappers you built. Catalogue, not runtime: say which
  enforcement class it lands in, and **what it cannot detect**.
- `python tools/report-installed.py` — regenerate this machine's `installed/<HOST>.md` so the
  record of what is actually wired here stays true. Record anything **declined** and why, in the
  hand-written section, so the next conductor does not re-litigate it.
- **Push to `main`.** This repo has no review gate; unpushed means it does not exist.

**B. Conductor guidance + status-page tooling.**
- `docs/conductor-brief.md` — the contract. Fold in anything a kickoff prompt started
  accumulating; a rule that lives in two places has already begun to drift.
- `docs/needs-you.md` — Brad's carried instructions. **Check every open item against what was
  actually decided this run** before handing it on; a stale entry costs him a real round trip.
- `docs/decisions.md` — the rolling snapshot, always current.
- Status-page tooling (`tools/conductor-status.py`, `tools/status-server.py`,
  `tools/status-page/`) plus any hook/skill/script changes → **sync to `dotfiles-bs` and verify
  it landed by comparing checksums, not by trusting the sync's success message.** An
  allow-list omission is silent by construction: the sync reported success on every run while
  the highest-value prose file in the setup was absent from the backup.

**Merging.** Guidance/practice repos (`agentic-practices-bs`, `dotfiles-bs`) — merge and push to
`main`, that is their normal flow. Product repos (`iotta-bs`, `iotta-firmware`) — **branches wait
for Brad unless he said otherwise for that branch.** Do not quietly widen a specific approval
into a general one; one run merged a status-page branch into the branch carrying the live tooling
rather than `main`, and its own note records that it *"made it worse and framed it as a fix."*

## Step 4 — Mechanical (delegate or script; never spend judgment here)

- `python iotta-firmware/tools/conductor-status.py` — regenerate the dashboard.
- `python iotta-bs/tools/check_docs.py` — the generated index must not be stale.
- Commit **and push** everything; unpushed work is invisible to a deploy and to the next run.
- Verify the bench is on known-good firmware and not mid-experiment. **Never leave a board
  on a knowingly-broken image** — restore it or say loudly in `needs-you.md` that it is not.
- Confirm the state backup ran (the pacer checkpoints it; verify rather than assume).

## Step 5 — Spool unread input, then schedule the successor

If Brad sent messages you did not fully act on, **do not drop them and do not pretend you
did**. Append them verbatim to `needs-you.md` under "unprocessed input", with one line each
on why they were not handled.

Then schedule the successor with `create_scheduled_task` (`fireAt`, one-time) if the work
warrants a follow-on run. The prompt must be **self-contained** — the successor remembers
nothing. Point it at the brief and `needs-you.md` rather than restating them; a scheduled
prompt that duplicates the brief is a fourth place for the same content to drift.

## The test for whether this worked

**Not** "did I write a handoff." It is:

> Could a conductor who has never seen this session pick up the highest-value in-flight
> work within ten minutes of reading the brief, `needs-you.md`, and the dashboard —
> without asking Brad anything?

If not, the wind-down is incomplete, regardless of how much was written. Length is not the
deliverable; a cold start is.
