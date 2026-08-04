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
