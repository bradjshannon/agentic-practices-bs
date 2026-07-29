# Read your own context usage from the transcript, not from a relay

**Class:** measurement source. Replaces a relay that can silently stop relaying.

## The problem it fixes

An agent cannot observe its own context-window utilization directly. The documented workaround is
`statusLine`, which *is* handed `context_window.*` and runs after every assistant message — so a
statusLine script can relay the numbers to a file the agent reads on demand.

**But `statusLine` only fires in the interactive terminal UI.** In a scheduled run, or in a desktop
client, nothing calls it, and the relay file keeps whatever the last interactive session left. It
does not empty; it *freezes*. A frozen reading is indistinguishable from a live one.

Two failures came from this. A run wound down at 32% believing it was near 70%, throwing away two
thirds of its window. A later run found the file holding a **test invocation** from six days earlier
— `session_id: "test"`, `cwd: "D:/x"` — and had no number at all.

## The mechanism

Claude Code appends every assistant message to `~/.claude/projects/<slug>/<session-id>.jsonl`, and
each carries a `usage` block. Read the last one:

```
used = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
```

`cache_read` dominates and is the field most easily forgotten; omitting it understates usage by
orders of magnitude on a long session.

`scripts/context-now.py` does this. Three properties worth copying:

- **It refuses rather than guesses.** No transcript, or no usage block, exits non-zero with the
  reason. The whole point is that a wrong number is the failure being prevented.
- **It reports the transcript's age and flags it stale.** The source can only go stale if the
  session is dead, but saying so is free and makes misuse visible.
- **It defaults the window to 1M, not 200k.** A 200k assumption overstates usage roughly 5× on
  current models, which is exactly the direction that causes premature wind-down.

## The slug detail that will bite you

The project directory name is the working directory with **every non-alphanumeric character**
replaced by a dash — separators, colons *and dots*. So `D:\GitHub\proj\.claude\wt` becomes
`D--GitHub-proj--claude-wt`. A separator-only replacement produces `...-.claude-...` and finds
nothing. Written down because it cost a debug cycle.

## What it cannot detect

- **Which transcript is "yours"** when several sessions share a working directory. It takes the most
  recently written, which is right in practice and wrong if a sibling session is more active. A hook
  receiving `transcript_path` would be authoritative; this is the on-demand approximation.
- **The window size**, which is inferred from the model name and defaults to 1M. Wrong for a small
  model.
- **Usage since the last assistant message.** It is as current as the last completed turn, so it
  lags by exactly one turn — fine for a wind-down decision, not for a mid-turn budget.

The general shape: **when a measurement reaches you through a relay, ask what happens when the relay
stops running.** If the answer is "the last value persists", the relay can lie indefinitely and you
want the primary source instead.
