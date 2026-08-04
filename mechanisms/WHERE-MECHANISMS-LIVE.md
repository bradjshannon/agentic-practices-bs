# Where mechanisms live

`mechanisms/README.md`'s ranking table (Structural / Instrumented / Interrupt /
Guard-at-the-action / Voluntary) answers *how strong* a control is. This doc answers a
different question that turned out not to have an existing answer: **for a given piece of
machinery, where does it physically live, and how does the copy that runs get the copy that's
committed?** Written after a session spent hand-diffing a hook against its own banked copy to
discover they'd already drifted — which is exactly the kind of thing a doc like this should
have made unnecessary to discover by hand.

## The general shape

Almost everything here that actually *runs* exists in two places at once:

- **The machine copy** — installed somewhere a harness reads at runtime (a hooks directory, an
  agents directory, wherever the tool expects it). This is the copy that is *live*.
- **The repo copy** — committed, reviewable, shareable across machines and projects. This is
  the copy that is *durable*.

Neither one is allowed to be the only copy. A machine-only file cannot be reviewed, diffed, or
carried to a second machine, and it is one bad `rm` from not existing. A repo-only file is
inert — nothing reads it until someone installs it, and "committed" is not the same claim as
"in force" (see `mechanisms/README.md`'s own corollary: *"an entry here is not in force
anywhere"*).

So the real question for any artifact is: **what keeps the two copies from disagreeing?**

## The pairings, by kind

| Kind | Machine-side location (pattern) | Repo-side location (pattern) | Kept in sync by |
|---|---|---|---|
| Guard hooks (PreToolUse / Stop / SessionStart / etc.) | a hooks directory the harness reads on the matching event | `mechanisms/hooks/<name>.py` + `<name>_test.py`, both loaded **relative to the test file** so a test proves the *banked* copy, not whichever one happens to be installed | **Nothing, currently.** Found live this session: a hook had a rule on the machine that had never been banked. No tool detects this; a human or an agent has to think to `diff` the two files. |
| Agent/role definitions (system prompt + tool allowlist + model) | an agents directory the harness reads by name | a `machine/agents/<name>.md`-shaped path in the private tactical repo | a small sync tool that **checks** drift and **requires a human-or-agent-named direction** to apply it — it never guesses, because both sides are legitimately hand-edited |
| Scheduled-task entry points | a scheduled-tasks directory the scheduler reads | same private-repo pattern as agent definitions | the same sync tool, same no-guessing rule |
| Liveness/heartbeat instruments (a self-arming timer that re-invokes a stalled run, a context-budget reader) | installed at the top level of the machine's config directory, called by a bare filename | a versioned copy inside the private tactical repo's per-project tooling | the same sync tool — added to its checked-file list only *after* drift was found twice, which is itself the pattern worth noticing: **the sync tool's own coverage list is Voluntary until something drifts and gets noticed** |
| Verification / structural-commit scripts (prove a claimed write actually happened, not just that the command exited 0) | not installed — called **by path** from wherever it's cloned | `mechanisms/scripts/<name>.py` | not applicable — there is only one copy, because nothing needs a machine-local install step to be callable |
| Sanctioned single-writer tools for a structured data file (the poka-yoke pattern: one tool owns all writes to one `.jsonl`, and it re-reads after writing to *prove* the write resolved, not just that `json.dumps` didn't raise) | not installed — called by path, same as verification scripts | lives in the private tactical repo next to the data files it writes | not applicable, same reason |
| Doctrine / case-law prose (`lessons/`, this repo's own top-level `README.md`, `mechanisms/README.md`, a project's own "brief") | **not installed anywhere** — it is read, at priming, by an agent that chooses to read it | the repo itself | nothing keeps it "synced" because there is only ever one copy; its risk isn't drift, it's **decay through non-reading** |

## So — is a registry like `GUARD-LEDGER.md` itself a mechanism?

Asked directly, mid-session, and worth answering precisely rather than waving at: **no, not by
this repo's own ranking table.** Run the same test the table already uses — *does it work on an
agent that never read any of this?* `GUARD-LEDGER.md` blocks nothing, interrupts nothing, and
nothing fails to build if a row goes stale or is never added. It requires an agent to remember
to add a row, honestly, after actually running both the firing and the silent case. That is the
literal definition of **Voluntary** two rows up the table — the same class as a `lessons/`
entry, not the class of the guards it describes.

That is not a knock on it — a Voluntary-class registry can still be *useful*, the same way a
lesson is still useful. But its usefulness is bounded exactly the way the table predicts:
nothing stops a ledger row from going stale the moment the guard it describes changes, the same
way nothing stopped a hook from drifting between its machine copy and its banked copy until a
session happened to notice. **A registry ABOUT mechanisms is not itself Structural just because
it talks about Structural things.** If `GUARD-LEDGER.md`'s claims ever need to be trustworthy
without a human re-reading them, the honest next step is the same one this table keeps pointing
at: make staleness Instrumented (a check that reads the ledger's dates against the guard files'
own mtimes/hashes) rather than trusting the next author to have read this paragraph.

The corollary, stated once because it applies to every doc in this list including the one you
are reading: **a description of a mechanism is not the mechanism.** This file, `README.md`,
`mechanisms/README.md`, and `GUARD-LEDGER.md` are all Voluntary. Only the things in the
left-hand column of the table two sections up are not.

## "Is this workstation up to par?" — a different question, and it needs a different instrument

Asked 2026-08-04: *"I want that ledger to serve as a check for 'is this workstation up to par?'
but maybe that standard will vary from user to user … so there has to be a way to opt-out of
mechanisms. and if mechanisms can be auto-synced, we need settings for that too."*

**The premise needs correcting before the design makes sense.** `tools/check_guard_ledger_freshness.py`
is not, and cannot become, a workstation check. It reads `mechanisms/hooks/` **in this repo** and
runs the banked test each ledger row cites. It never looks at a hooks directory, never looks at a
harness config, and would give the same answer on a machine with nothing installed at all. It
answers *"are the ledger's claims still true?"* — a repo question, which is why it runs in CI.

That distinction is load-bearing for the opt-out, not pedantry. **Opting out of a guard does not
make a failing banked test acceptable.** If a workstation declines `hardware_hedge_guard`, the row
asserting that guard's evidence is still either true or false about this repo, and a false one must
still fail. Wiring per-machine opt-out into the freshness checker would mean a machine could switch
off the repo's own integrity check — the control-plane equivalent of letting the thing being
measured set the threshold. So:

| Question | Instrument | Scope | Opt-out? |
|---|---|---|---|
| Are the ledger's claims still true? | `tools/check_guard_ledger_freshness.py` | this repo, environment-independent | **No.** A claim is true or it is not. |
| Can this environment even run the check? | same script, verdict `UNRUNNABLE` (exit 2) | per-run | n/a — reported, never folded into pass or fail |
| Is this workstation carrying the mechanisms it means to? | **does not exist in this repo** | per machine | **Yes — this is where opt-out belongs.** |

The third row is what Brad is asking for, and the third-row instrument is the one to build. Two
partial ancestors exist in the private tactical repo — a generated installed-mechanisms report and
a pre-run presence/wiring check — and between them they already prove the shape works. What neither
has is a *declared intent* to compare the machine against: they report what IS installed, so a
mechanism that was never installed and a mechanism that was deliberately declined are
indistinguishable, which is the same "absence is not evidence" failure this repo keeps naming.

### Opt-out and auto-sync are one table, not two features

This is the part worth stating plainly, because treating them separately is the expensive mistake.
A sync tool's first question is *"should this machine have this file?"* — which is exactly the
opt-out answer. A machine that declined a mechanism must not have it pushed back by the next sync,
and a machine that wants one has just told the sync tool to install it. One row per mechanism, and
the three columns a sync tool and a conformance check both need:

- **`want`** — `yes` / `no` / `pin:<rev>`. `no` is a *decision*, and a conformance check must report
  a declined mechanism as DECLINED, never as MISSING. That is the whole point: a machine below par
  and a machine deliberately configured differently must not render the same.
- **`sync`** — `auto` / `manual` / `never`. Not a global setting: hooks are code that runs on every
  tool call, and the standing rule that a sync direction is never guessed applies per file, not per
  repo. `manual` is the correct default for anything hand-edited on both sides.
- **`why`** — free prose, authored, never generated, preserved verbatim across regenerations. The
  mechanical half is derived on every run; the judgement half is the half a regeneration must not
  destroy.

Two things follow that are not obvious. First, **the manifest cannot live in this repo**: it names
a machine, and this repo's own sanitizer forbids that — so the catalogue is public and the manifest
is per-machine (machine-side file, mirrored into the private tactical repo). Second, **hooks
currently have no sync path at all** — the top table's first row says so — so `sync: auto` has
nothing to execute until one exists. That ordering is a real dependency: the manifest is worth
building first regardless, because it makes DECLINED expressible, which nothing today does.

**Settled 2026-08-04 by Brad: granularity is PER MECHANISM.** Per-class stays available as a later
convenience; it is not the only knob, because a class-level decline silently absorbs any mechanism
added to that class afterwards.

### The question is not academic — it was answered empirically, badly, the day it was asked

Looking for the third instrument's shape, 2026-08-04, three findings turned up on one workstation
that no existing check covers, and each is a different *kind* of not-up-to-par:

- **A repo's own pre-commit gates were not installed.** A project whose brief states in the present
  tense that a doc-check "rejects any commit that puts an item ID in this file" had a seven-hook
  `.pre-commit-config.yaml` and no `.git/hooks/pre-commit` at all. Nothing watches this: the
  installed-mechanisms report reads the *harness's* hooks directory, not any repo's. So a mechanism
  the ledger classes **Structural** was Voluntary here, and its class was never wrong in the
  ledger — it was wrong *on this machine*, which the ledger's format cannot express.
- **A pre-run check silently stopped answering half of what it checks.** Its repo list held absolute
  paths from a different machine's clone root, so it reported three repos "not cloned" while all
  three were cloned and one was the repo it was running from. "Absent" and "elsewhere" rendered
  identically for long enough that the WARN became background noise.
- **A live instrument had drifted in without being recorded.** Regenerating the installed report
  picked up a hook wired on two events that the repo's record of the machine did not mention.

Three different failures, one shape: **nothing compares what is running against what was intended,
because nothing writes down what was intended.** That is the manifest's whole job, and it is why
the recommendation above is to build the declared-intent column rather than a new subsystem — two
of these three would have been caught by a manifest plus a diff, with no new checking machinery at
all. The third (git hooks) needs one new probe, which is `.git/hooks/` per declared repo.

*(A fourth turned up while answering Brad's follow-up: the fix for the second finding above still
reported one repo "not cloned" when it was cloned — under `$HOME` rather than a `GitHub/` root,
because it is a dotfiles repo and that is where dotfiles repos go. I asserted that WARN was a true
positive, in a commit message, and used it as the positive control for the other two. Replacing a
hardcoded path with a slightly-less-hardcoded list of paths reproduces the same defect at lower
amplitude, and a control you have not checked is not a control.)*

### Correction: hooks live in THREE places, not two, and the third one already works

The top table's first row says hooks are kept in sync by *"Nothing, currently."* That is right about
the pair it names and **wrong about the population.** There is a third copy, and it is the healthiest
of the three: a per-host automated backup repo that mirrors an allow-list of `~/.claude` into
`<HOSTNAME>/.claude/`, committing and pushing on a ~20-minute timer. `hooks/` is on its allow-list.

Measured across all 21 installed-or-banked hooks on one workstation:

| | count | meaning |
|---|---|---|
| machine ≡ backup | **21 of 21, byte-identical** | the backup is current and one-way; it is never stale |
| machine ≡ banked catalogue | 11 | in step |
| machine ≠ banked catalogue | **6** | drifted silently, four of them with ledger rows |
| backed up but never banked | 4 | on the machine and in the backup, absent from the catalogue |
| banked but NOT installed | 1 | has a ledger row and a green test; is not running here |

Three copies, three jobs, one keeper between them:

- **machine** — live, and the authority for everything hand-edited here.
- **per-host backup repo** — *derived*, one-way, current, per-host. Excellent for restore. Useless as
  an authority: its sync does `rm -rf <dest>; cp -r <src>` per item, so anything authored on the repo
  side is destroyed on the next cycle. Its allow-list is deny-by-default and its own comments record
  that omissions from it are **silent by construction** and have already bitten twice.
- **banked catalogue (this repo)** — shareable, reviewable, hand-edited on both sides. Nothing keeps
  it in step with the machine; the 6 drifted hooks are what that costs.

**That last table row is the whole question in one line.** A hook that is banked, tested green, and
not installed is either a deliberate decline or an accidental omission, and **no instrument can tell
which**: the freshness checker says FRESH (correct — the repo's claim holds) and the installed report
says not-wired (correct — it is not running). Both are right, neither is the answer, and the missing
thing is a written-down intent.

### Is the per-host backup repo the right home for the manifest?

**Yes for the namespace, no for the file location — and that distinction is the answer.** It already
has the per-machine partition, one directory per hostname with both workstations present, which is
exactly what a manifest needs and which no other repo has. But the manifest cannot be authored *into*
that repo: the next sync cycle deletes and rewrites the directory from the machine.

The routing that works, and needs no new machinery at all: **author the manifest under `~/.claude/`
and add its filename to the sync allow-list.** It is then backed up per-host automatically, in the
right namespace, versioned and pushed, in the correct one-way direction — and the machine stays the
authority, which it must be for a file describing that machine.

**Do not move the hand-edited-on-both-sides files there.** Agent definitions and briefs are edited on
the machine *and* in the repo, which is exactly why their sync tool refuses to guess a direction. A
one-way destructive mirror would resolve that ambiguity by destroying one side every 20 minutes. The
rule that falls out: **anything authored on the machine and only ever read elsewhere belongs in the
per-host backup; anything authored in two places must not go near it.** The manifest is the former.
So is the answer to "is it a better place for machine-specific conductor files" — for the derived and
machine-authored ones, yes; for the mirrored ones, no, and the distinction is not about the files
being machine-specific, it is about how many places author them.

### Auto-sync scope: updates may auto-apply, add/remove/destructive must not

Brad, 2026-08-04: *"we have an option for auto-UPDATES but never an option for auto-ADD/REM actions.
Add/rem, as well as potentially destructive updates, need to be raised for the user's approval."*

Right, and it turns `sync` from a per-file switch into a per-file switch **plus a per-operation floor
no switch can lower**:

| operation | may `sync: auto` apply it? |
|---|---|
| update; exists both sides; one side strictly newer, the other unchanged since the last common state | yes |
| update where **both** sides changed since the last common state | **no — gated** |
| add (present one side, absent the other) | **no — gated** |
| remove | **no — gated**, always, whatever the setting says |

The floor matters more than the setting. An *add* is precisely the case where nothing can know
whether the file is new-and-wanted or declined-and-absent — which is the question the manifest
exists to answer — so until a manifest row says `want: yes`, an add is a question, not an update.

**The surface for raising it already exists; do not build a fourth one.** The nagging agent described
above is the status-page card: it carries the exact command, re-evaluates its own premise on every
render, will not go away while the premise holds, and retires itself the moment the situation is
fixed. That pattern was used for one of the findings above on the same day it was found. What is
missing is not a TUI — it is that the existing drift check classifies drift only as "which side is
newer" and prints it to a console nobody reads unattended. It should classify each drift as
update/add/remove and **file a card for every gated one.**
