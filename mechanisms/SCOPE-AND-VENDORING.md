# Scope and vendoring

`mechanisms/README.md`'s ranking table answers **how strong** a control is.
[`WHERE-MECHANISMS-LIVE.md`](WHERE-MECHANISMS-LIVE.md) answers **where a copy lives and what
keeps two copies from disagreeing** — the durability axis, machine copy vs repo copy.

This file answers the third question, which had no answer: **how many projects does this
mechanism fire in, and how does a repo or a machine that wants one actually get it?**

The question was asked directly: *"do we have a record of good ideas for repo-scoped
hooks/guards, or is it entirely focused on system-wide stuff?"* The measured answer was
**entirely system-wide.** Every mechanism in `mechanisms/hooks/` installs to a harness hooks
directory and fires in every project. The only acknowledgement anywhere in the corpus that
repo-scoped guards exist is one line at the top of `GUARD-LEDGER.md` telling you to copy the
ledger into any repo that owns guards. Meanwhile eleven repo-scoped hook entries were already in
production across two repos, and none of them were in the corpus.

---

## SETTLED — marked regions, and the tooling enforces the boundary

**May a vendored mechanism be edited in the repo that consumes it?**
**Inside its declared regions, yes. Outside them, no, and the tool refuses rather than clobbering.**

The operator asked for exactly this on 2026-08-10 — *"can we have sections of code that are
overwritten on updates from upstream, but other sections that the user can alter safely?"* — and it
was built the same hour: `conductor-pub/tools/conductor_graft.py` plus
`conductor-pub/docs/marked-regions.md` (`4cedfc4`, then `eafc077` closing three falsifications of
"nothing can be lost"). Upstream owns the file and declares the regions; the consumer owns what is
inside them; an edit *outside* a region makes the next update exit non-zero with `CONFLICT` instead
of overwriting silently.

Verified end to end rather than read: an adopt → check → apply cycle on a Python hook, where
upstream's out-of-region change landed while the consumer's in-region line survived byte-for-byte,
and a deliberate out-of-region edit produced `CONFLICT`, exit 1. **It is not skills-only** — nothing
in `conductor_graft.py` filters by path or suffix, and `#` is one of six recognised comment openers.

⚠️ **This section previously read `OPEN FORK — needs the operator's call before anyone builds this`
and recommended a read-only mirror plus a lock file. That is quoted here for audit because the
recommendation was acted on elsewhere:** the same framing reached a decision card, which then sat on
the board for sixteen hours asking a question the operator's own comment had already closed.

What the old text got right and is worth keeping: hand-editing both sides is what forced
`conductor-sync.py` to refuse to guess a sync direction, and once both sides are authored no tool
can tell a local improvement from a stale copy. Marked regions answer that by making the ownership
boundary *declared and machine-checked* rather than inferred — which is why the fork dissolved
instead of being decided.

**What is genuinely open is work, not a decision:** no mechanism carries a region yet, and the four
hooks shipped in `conductor-pub/hooks/` are 31–59% similar to their twins in this corpus with
nothing reporting the gap. Comparator first, manifest second.

A second question that looks like a fork and is not: **where a repo-scoped mechanism's
authoritative copy lives.** For the three genuinely portable tools identified below, this corpus.
For the rest, the repo that owns them, next to the failure they were written for. A repo's own
test suite and its own UI checks are not vendoring candidates and never will be; pretending
otherwise fills a corpus with things nobody can adopt.

---

## The two halves of one declaration

The machine-side half is **decided**. The mechanism-side half is **open**. They are two sides of
one design and reading either alone will produce the wrong thing.

| half | who declares | what it says | status |
|---|---|---|---|
| **machine → mechanism** | that machine's owner, by hand | `mechanisms.toml`: `want` (`yes`/`no`/`pin:<rev>`), `why` | **DECIDED, UNBUILT** |
| **mechanism → machine** | the mechanism's author | what this thing is, what it needs, what to do when it cannot run | **open — evaluated below** |

### The machine half: decided, and it has no code behind it

The selected multi-workstation model is *"shared with partition: one git repo, shared domain state
converges by union-merge, `[repos]` paths and `mechanisms.toml` partitioned per workstation."*
`mechanisms.toml` is per-machine declared intent — **partition class: never merged, never
overwritten from elsewhere** — living at `workstations/<ws-id>/mechanisms.toml` beside that
machine's config overlay and its derived installed-report.

**Verified while writing this: the container is built and the file is not.** The workstation
partition, the `.workstation` declared id, the per-key config overlay and the cubby registry all
have implementations and tests. `mechanisms.toml` appears **only in prose and data** — a proposal,
a decisions archive, an inbox, one machine's installed report — with **zero occurrences in any
`.py` or `.toml` in either repo.** So it is a decided artifact with nothing reading or writing it,
which is the state most likely to be mistaken for a built one.

Two properties of the decided design carry over to anything built on it, and both are
load-bearing here:

- **The workstation id is declared in an untracked file, never sniffed**, and a missing id reports
  `UNCLAIMED` rather than guessing — *"not even when exactly one partition exists, which is the
  tempting wrong behaviour."* Any mechanism-side declaration must inherit that: **an unresolvable
  requirement is reported, never inferred.**
- **Partition, not merge.** A machine's `want: no` must never be reconciled against another
  machine's `want: yes`. This is why the intent file cannot be a corpus artifact — the corpus is
  shared, the intent is not.

### The mechanism half: is `scope` even the right axis?

The sketch on the table was a filename prefix — `global_x.py`, `repo_y.py` — offered with an
explicit invitation to do better. Two separate questions hide in it: *where should the declaration
live*, and *what should it declare*. They have different answers.

**Where: in the file, as a field — not in its name or its directory.** The prefix has one genuine
advantage that should not be dismissed: it needs no reader. It is visible in `ls`, it works on an
agent that never read any of this, and there is no parser to break. Most proposals in this corpus
cannot claim that. But it fails on four counts, and the first was measured in this corpus while
this document was being written:

1. **Path-encoded classification has already produced a false negative here.** Two hooks —
   `estimate_tracker.py` and `tool_output_volume.py` — live in `mechanisms/scripts/`, not
   `mechanisms/hooks/`, despite being PreToolUse/PostToolUse hooks. A survey conducted by
   directory concluded both were unbanked and machine-only. They were neither: both were already
   in the repo, byte-identical to the installed copies, and the near-miss was banking duplicates.
   Encoding a mechanism's class in its *location* is the same trick as encoding its scope in its
   *name*, and it has already drifted once without anything noticing.
2. **A rename breaks every reference.** A consuming repo names the script by path in its
   `.pre-commit-config.yaml` `entry:` line; so do ledger rows, README tables and install notes.
   Changing a mechanism's scope would mean a rename plus a sweep of every pointer — the exact
   restatement-rot this estate keeps building machines to kill.
3. **Nothing verifies a prefix.** `global_foo.py` is an assertion in a filename, and nothing fails
   if it is wrong.
4. **A field has a consumer path; a prefix does not.** `mechanisms.toml` is the reader, already
   decided. A prefix cannot be joined to it.

State the limit honestly, though: **a header that nothing parses is exactly as decorative as a
prefix.** Neither is a mechanism until something reads it. The field's advantage is not that it is
enforced today — it is that it can *become* enforced without a rename.

**What: `scope` is the least useful of the fields worth declaring, and I would not build around
it.** This is the part of the sketch to push back on. Reading the eleven, the questions an
installer or a conformance check actually needs answered are:

| field | what it answers | why it earns its place |
|---|---|---|
| `requires` | what must exist for this to run at all — a harness event, a language toolchain, an external tool, a sibling repo | **This is the field that would have caught the `tools-index` sibling-clone dependency.** Today that requirement exists only as an inline `[ -f "$g" ]` test inside a bash string in one repo's config, where nothing can read it. |
| `on_unavailable` | `skip` or `fail`, when `requires` is not satisfied | The single most valuable field, and the prefix idea has no room for it at all. See the `--gate` asymmetry below. |
| `blocking` | rejects the commit, or advisory | Two of the eleven are deliberately advisory. Conflating them with the blocking ones misreads both. |
| `scope` | global / repo / both | Necessary, but weakest: it is usually inferable from where the thing is installed, and it rarely changes. |

**So: declare requirements and unavailability behaviour, and let scope be one requirement among
them.** Scope is the axis that names the *symptom* the operator noticed — a corpus full of global
things — but the axis that carries information is what a mechanism *needs* and what it does when
it cannot have it.

A third option worth naming and rejecting: **a separate index file listing which mechanism has
which scope.** That is a registry about mechanisms, and `WHERE-MECHANISMS-LIVE.md` already settled
what those are worth — Voluntary, stale the moment the thing it describes changes. The field
belongs *on* the artifact.

---

## Neither half detects drift, and that is how tonight's divergence happened

**`mechanisms.toml` records intent. It does not record what is actually installed, nor whether the
installed copy still matches its source.** Those are three different facts, and this estate has now
been bitten by the gap between them in both directions on one evening:

- Six hooks were believed to exist only on the machine. **Two of the six were already banked and
  byte-identical** — an intent file would have been just as wrong, because intent says what
  *should* be there, not what *is*.
- One hook existed only in the repo and had never been installed.
- `stale_cache_guard_test.py` resolved its subject through a hardcoded install path, so **the
  banked copy silently tested the installed copy.** A regression in the banked copy could not have
  failed its own test. Nothing about that is visible to a manifest.

**What closes it, and the build order is the opposite of the obvious one.** The cheapest instrument
is a **content comparison between the banked copy and the installed copy**, per mechanism,
reporting `IDENTICAL` / `DRIFTED` / `NOT-INSTALLED` / `NOT-BANKED`. It needs no manifest, no
installer, and no new format — it was run by hand over eight files tonight in a single command, and
it is what turned "six machine-only hooks" into "four machine-only hooks and two false alarms."
The manifest adds exactly one thing on top: the ability to distinguish **DECLINED** from
**MISSING**, which is real and is `WHERE-MECHANISMS-LIVE.md`'s own argument — but it is the second
increment, not the first. A manifest without a comparator records intentions nobody checks.

The cost is low and worth stating plainly: the comparator is a directory walk and a hash per file.
What it cannot do is tell you whether the installed copy is *wired* — a hook present in a directory
but absent from the harness config is `IDENTICAL` and inert. That is a third probe, and it is the
one `tools/check_workstation.py` already exists to make.

---

## `[repos]` and the `tools-index` silent skip are the same problem

This is the catalogue's most damning example, and it turns into a worked argument for the decided
design.

`myproject-server`'s `tools-index` pre-commit hook resolves its vendored generator through a hardcoded
relative sibling path:

```
g=../conductor-bs/tools/gen_tools_index.py
if [ -f "$g" ]; then python "$g" --repo .; else echo "tools-index SKIPPED -- $g not present"; fi
```

If the sibling clone is not at that relative path — a worktree, a fresh clone, the other machine,
CI — the hook prints one line and **exits 0**. The commit passes. Nothing distinguishes "the index
was checked and is current" from "the index has never been checked at all." That is this corpus's
archetypal failure, the one `GUARD-LEDGER.md` opens with: a wrapper ending in a bare `exit 0` so
every build reported success, while the guard-shaped thing in the middle had never once been
observed doing its job.

**The author's reasoning was sound and should not be reversed.** One generator serving four repos
is right — the alternative is four copies plus a fourth parity-check to police them, which that
generator's own docstring says it is deliberately avoiding. And a hook that fails for a reason its
author cannot act on gets `--no-verify`'d, which is worse than skipping.

**The defect is that a per-machine filesystem fact is baked into a shared, committed file.**
`../conductor-bs/tools/` is true on one machine's layout and false on another's, and the shared
file has nowhere to say so. That is exactly the class `[repos]` exists for: a per-machine
alias→path table living in the partition, merged per alias so a machine overrides the paths that
differ and inherits the rest.

Resolving the generator through an alias rather than a relative path changes the failure from
invisible to actionable: instead of `SKIPPED — file not present`, an unset alias on this machine
is a named, per-machine gap that a conformance check can report and the machine's owner can fix by
editing one line in a file that is already theirs. **It does not require making the hook
blocking** — which would reintroduce the `--no-verify` problem — because the reporting moves out
of the commit path and into the machine's own conformance surface, where an unactionable failure
costs nobody a commit.

The residual, which `[repos]` does not fix and should not be claimed to: **a skip still needs to
age.** Nothing today records that this repo's index was last genuinely verified on some date, so a
repo that has skipped for months looks identical to one that checks on every commit. A skip that
is recorded and aged is fine; a skip that prints to a console nobody reads is the failure. Either
the generated index carries a `generated-at` line the check compares, or the skip writes a stamp
into the repo's freshness registry so a sweep can report *"this gate has not actually run in N
days."*

---

## The eleven, with a portability verdict from reading each source

**They are eleven hook entries but ten distinct programs** — `tools-index` appears in both repos,
invoking the same generator. Counting hook entries rather than tools inflates the apparent size of
the portable set, which is the first thing to correct. **Not all eleven are portable, and the
honest portable set is small.**

### Genuinely portable, little or no change

| Mechanism | What class of defect it catches | Why it is portable | Cost to adopt |
|---|---|---|---|
| `gen_tools_index.py` (`tools-index`, both repos) | Hard-won tooling invisible to the next agent, who rebuilds it. Measured: 55 tool scripts across four repos, 34 of them (62%) appearing in no priming path. | Already takes `--repo <path>` and generates from that repo's own `tools/` only. It **extracts** from each script's existing module docstring rather than requiring anything to be written, so an adopting repo authors nothing. No repo-specific knowledge in the tool. | One hook entry and one generated file — plus the vendoring decision above, since this is the mechanism whose current path-reference vendoring silently skips. |
| `check_discarded_returns.py` (`discarded-returns`) | A call to a known-fallible function whose return value is discarded. The motivating incident: a `mkdir()` that failed silently on an over-length path component, misread as a physically removed SD card and published into telemetry as a false hardware claim. | Language-scoped (C/C++), not repo-scoped: a fixed list of ten C stdio/POSIX functions and one syntactic shape. Nothing in the matcher knows anything about the project. Its false-positive rate was measured and driven to **0 across the whole tree** before it was wired in — the precondition that makes it adoptable at all. | Drop in, scope by `files:`. Budget the same measurement pass on a new tree before wiring it as blocking. |
| `failure_mode_hunt_diff.py` (`failure-mode-hunt-drift`) — **as a pattern** | An advisory scanner whose coverage silently drifts away from evolving source. Its own insight is the portable part: **a bare finding count cannot distinguish a fix from a broken matcher.** 7 → 5 is equally consistent with two findings fixed and with someone loosening a regex. | Reports the *set difference* — NEW vs RESOLVED — against a checked-in baseline, fingerprinting each finding as `(rule, path, enclosing-function)` rather than by line number, so unrelated edits do not show 100% churn. That design is independent of the scanner underneath. | Portable **with parameterisation**: the file is coupled to its scanner's finding shape and needs a fingerprint adapter for a different one. |

### Portable as a convention, not as a file

- **`check_freshness_claims.py --gate`** (`dram-guard-threshold`). The claims it checks are
  entirely local — a DRAM-headroom constant mirrored between an SDK and a firmware repo because
  the SDK exposes no callback to observe the decision. **The portable idea is the `--gate` flag's
  two-consumer asymmetry:** a comparison that *cannot be made* fails a freshness sweep but skips a
  commit gate. Same code, two strictnesses, because a gate that blocks a commit for a reason its
  author cannot act on gets bypassed, and a bypassed gate enforces nothing. This is the correct
  version of the `tools-index` skip above — same author, same repo — and it is the direct
  ancestor of the `on_unavailable` field proposed earlier.
- **`test_check_docs.py`** (`doc-checks-tests`). Unit coverage for the checker, wired as its own
  pre-commit hook beside the check it tests, so a broken checker fails *before* the check it would
  have run. Trivially general and almost never done: most repos gate on their guards and never
  gate on their guards' tests.
- **`pytest` (server suite)**, **`ui-test`**, **`ui-typecheck`**. Not vendorable — a repo running
  its own tests, and inherently repo-specific. **The portable artifact is the scoping convention**,
  and it was paid for: the `pytest` hook used `types: [python]`, so a 19-file push of docs, JSON
  evidence and four throwaway analysis scripts — zero files under `server/src/` or `server/tests/`
  — ran a 3766-test suite, exceeded the pushing agent's tool timeout, and got `--no-verify`'d. It
  is now scoped by `files:` like everything else. **Scope a hook by path, never by file type**, and
  include the config file itself so a change to the hook re-runs it.
- **`server-status-smoke`**. The instance is local — a smoke test for one status page. **The
  general mechanism it implies does not exist anywhere and should:** the file was named
  `smoke_test.py`, matched pytest's default discovery pattern, and *no suite was ever pointed at
  its directory*, so nothing collected it. The cost was a panel that had never rendered once —
  every estate-health badge showing a `NameError` from a bare `urlopen` in a module that only
  imported `urllib.request`. A portable check would assert that **every test file in a repo is
  collected by some suite**: the general form of "a check nothing runs is not a check."

### Not portable

- **`check_docs.py`** (`doc-checks`, 876 lines). Deeply specific: it enforces one project's
  queue-id syntax, regenerates that project's `TODO-index.md`, and parses its `**Blocks:**` /
  `**Related:**` marker grammar into a tracked edge JSON. Not a vendoring candidate as a unit.
  **Two of its five check families are extractable and general**, and are the ones worth lifting if
  anyone does the work: `no_bare_counts` (a numeric claim with no attached check is a claim that
  will rot — that project's test count appeared as 44 / ~1200 / ~1763 / 1930 / 2042 across four
  files, none correct, settled in 55 seconds by one command nobody ran), and the citation checker
  (a doc names a `file:line`, a symbol or a branch as evidence, and the named thing moves without
  the prose).

**So the honest portable set is three tools, three conventions, and one mechanism that ought to
exist and does not.** That is a short list, and a short honest list is the useful output. Most of
the eleven are correctly where they are.

---

## What this document's own enforcement class is

**Voluntary**, by this repo's own ranking table, and it should be read with the same discount
`WHERE-MECHANISMS-LIVE.md` applies to `GUARD-LEDGER.md`. Run the table's test — *does it work on an
agent that never read any of this?* This file blocks nothing and interrupts nothing. Nothing fails
to build if a portability verdict here goes stale the day someone rewrites the tool it describes,
and nothing adds a row when a twelfth repo-scoped guard is written. It is the same class as a
`lessons/` entry, one step weaker than everything it describes.

**A description of a mechanism is not the mechanism.** That applies to this file exactly as it
applies to the others.

**What would make it Instrumented**, stated concretely enough to be a task rather than an
aspiration: a check that reads each mechanism's declared `requires` and **falsifies it against the
source** — a mechanism declaring no external requirement whose source contains an absolute path, a
hardcoded repo name, or a sibling-clone reference is contradicting itself, mechanically. That check
is buildable today, needs no new registry, and would have caught the `tools-index` sibling-clone
dependency the moment it was written. The declaration is its prerequisite, which is the real
argument for putting it in the file rather than in the filename.

---

## Where this file sits, and why

At `mechanisms/` root, beside `README.md`, `GUARD-LEDGER.md` and `WHERE-MECHANISMS-LIVE.md`,
because those three are the corpus's axis documents and this is the missing fourth axis: strength
(README), evidence (GUARD-LEDGER), durability (WHERE-MECHANISMS-LIVE), **scope and distribution
(here)**. It is deliberately not filed under `hooks/` — it describes no single mechanism — and
deliberately not a `lessons/` entry, since it is a design for machinery rather than an account of a
failure.

`GUARD-LEDGER.md`'s opening line — *"Copy this file into any repo that owns guards"* — was the only
repo-scoped statement in the corpus, and it now points here, because "copy the ledger" is the
smallest possible answer to a question this file answers properly.
