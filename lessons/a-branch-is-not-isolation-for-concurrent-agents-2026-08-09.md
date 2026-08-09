# A branch is not isolation — concurrent agents share one working tree

## Symptom

Three agents were dispatched in parallel, each told to create and commit to its own branch in the
same repository. Roughly fifteen minutes later a `git status` in that repo showed **seven modified
files belonging to two different agents at once**, on a branch belonging to a third:

```
$ git -C <repo> branch --show-current
feat/sanitizer-cannot-check          # agent A's branch
$ git -C <repo> status -s
 M src/conductorkit/core.py          # agent C's work
 M tests/test_core.py                # agent C's work
 M tools/check_sanitized.py          # agent A's work
 M tools/release_to_stable.py        # agent A's work
 ...
```

Nothing had errored. Each agent believed it was working in isolation, and each was correct about
its own edits and wrong about everything else in the directory.

## What actually happened

**A git branch is a ref, not a workspace.** All branches of a clone share one working directory, so
"put each agent on its own branch" isolates *commit history* and isolates nothing about the files on
disk. Two agents editing different files look fine right up until one of them runs a command that
touches the whole tree.

The dangerous operations are the ones that rewrite the working directory wholesale — `git checkout`,
`switch`, `restore`, `reset`, `stash`, `clean`. Any of those, run by one agent, silently carries,
reverts, or destroys another agent's uncommitted work. A `git checkout <my-branch>` is the natural
thing for an agent to do when it wants to commit, and it is exactly the thing that detonates.

Two things kept this from becoming data loss, and only one was deliberate:

1. **Every agent committed through a wrapper that stages explicit named paths and refuses extras.**
   So the blast radius was a bad *checkout*, not a bad *commit*. This was luck of convention rather
   than design — a plain `git add -A` in any one of the three would have swept the others' work into
   an unrelated branch.
2. **Two of the three agents independently created `git worktree`s** when they noticed the
   contention, without being told. The orchestrator's instruction was the flawed one; the agents
   routed around it.

The tooling already had the right primitive. The dispatch API exposed an `isolation: "worktree"`
option that creates a separate working directory per agent. It was simply not used, because
"each on its own branch" *sounds* like isolation.

## The rule

**When two or more agents may write to the same repository concurrently, give each its own working
directory — a `git worktree` or an equivalent — not its own branch.** If the dispatch mechanism has
an isolation flag, use it at dispatch; retrofitting isolation after agents are already running means
issuing corrections to processes that may be mid-write.

When isolation is not available and concurrency is unavoidable, the fallback is explicit and must be
told to every agent:

- **Never** run `checkout` / `switch` / `restore` / `reset` / `stash` / `clean` in the shared tree.
- Commit **only** explicitly named paths. Never `git add -A`, never `git add .`, never a wildcard.
- Treat a full-suite test run as untrustworthy: it executes everyone's half-finished edits, so a
  failure outside your own files is probably not yours. Report it; do not fix it.

## Why it generalises

This is the **shared-mutable-state bug in a place nobody looks for it** — the filesystem. Agent
frameworks encourage thinking of a subagent as an isolated worker with its own context, and that
mental model is right about context and wrong about disk. Anything the agents can all reach is
shared state: the working tree, a database, a running dev server, a fixed port, a scratch directory.

The tell is a plausible-sounding isolation story that names the wrong boundary. "Each agent has its
own branch", "each agent has its own table", "each agent uses its own filename" — each isolates one
axis while leaving the one that actually matters shared. The question to ask before dispatching
concurrent workers is not *"do they have separate identities?"* but *"what single mutable thing can
all of them write to, and what happens when two do?"*

A secondary lesson, cheaper but real: **the agents caught this before the orchestrator did.** Two of
them independently built worktrees. When several workers all route around the same instruction, the
instruction is the defect — that convergence is a signal worth reading rather than an inconsistency
worth correcting.
