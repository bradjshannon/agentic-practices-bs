# A worktree instruction does not propagate to repo-root-relative convention paths

**Date:** 2026-08-10. **Cost:** two of six subagents in one fan-out wrote their session files into
the *shared* main checkout — the exact directory the parent prompt told them never to touch.

## Symptom

Six subagents were dispatched, each with an explicit, repeated instruction in its prompt:

> Work ONLY in this worktree: `<repo>/.claude/worktrees/conductor-run`. NEVER write to `<repo>`
> directly — that's a shared checkout on another session's branch.

All six honoured it for their actual deliverables. **Two of them still wrote a file into the shared
checkout** — not their work product, but their *session-continuity bookkeeping* file, landing at
`<repo>/memories/repo/sessions/<timestamp>-<suffix>.md`.

Nothing failed. No error surfaced. The parent found it only by reading a completion report closely
enough to notice a path that looked one directory too short.

## What actually happened

The instruction and the violation live at different levels of abstraction, and the agents were not
being careless — they were following *two* instructions, one of which was invisible to the parent.

- The **parent prompt** scoped a directory: "work in this worktree."
- The **repo's own convention** (`CLAUDE.md` / `AGENTS.md`, which the orientation gate *requires*
  every agent to read before editing) scopes a path relative to the repo root: *"Create a new
  per-session file: `/memories/repo/sessions/YYYY-MM-DD-HHMMSS-<suffix>.md`"*.

An agent resolving that second instruction reaches for the canonical repo root, because that is what
a repo-root-relative path *means*. The worktree instruction governed where it was told to put its
work; it did not silently rewrite every other path the agent would later derive from a convention.

The two instructions never contradicted each other in any single sentence, which is why re-reading
the prompt does not reveal the bug. **The prompt scoped an action; the convention scoped a path.**

Aggravating factor that made it silent: `memories/repo/sessions/` is gitignored, so the stray files
could not be committed onto the stranger's branch and produced no `git status` noise. The blast
radius was small *by luck of that repo's ignore rules*, not by design. A convention pointing at a
tracked directory would have staged files onto another session's branch — a failure this estate has
already paid for once.

## The rule

**When you scope a subagent to a worktree, enumerate the paths its instructions will derive, not
just the paths you hand it.** Any convention the agent is required to read — session files, log
files, scratch output, cache locations — is a path *generator*, and a directory-scoping instruction
does not reach inside it.

Three ways to actually close it, cheapest first:

1. **State the derived path explicitly.** "Write your session file to
   `<worktree>/memories/repo/sessions/…`, NOT to the repo root." One sentence per convention.
2. **Sweep after the fan-out.** `find <shared-checkout> -newermt <run start> -type f` catches
   everything, including from agents that have not reported yet. Cheap, and it does not depend on
   having anticipated the convention.
3. **Make the convention worktree-relative at the source** — the durable fix, and the only one that
   survives a parent who forgets. If the repo's own instruction file says "relative to *your*
   checkout root" rather than showing a leading-slash absolute-looking path, the ambiguity is gone.

## Why it generalises

This is not about worktrees, or session files, or one repo's layout. It is the general shape:

> **A constraint expressed as a directory does not bind instructions expressed as conventions.**

The same failure appears wherever a scoping instruction meets an independently-authored path rule —
a container told to write only under `/data` whose logging library defaults to `/var/log`; a CI job
scoped to a build dir whose test framework writes coverage to the repo root; a sandboxed process
whose config resolver walks *up* to `$HOME`. In every case the scope was honoured for the thing the
author was thinking about, and quietly bypassed for the thing they were not.

The tell is always the same: **the violating write is bookkeeping, not work product.** Attention
follows the deliverable, so the deliverable lands in the right place and the metadata does not.

Corollary worth its own line: **a gitignore is not a guard, it is an accident of blast radius.**
The reason this cost minutes instead of hours is that the target happened to be ignored. Do not
read "nothing broke" as "the control worked" — nothing broke because the shot missed.
