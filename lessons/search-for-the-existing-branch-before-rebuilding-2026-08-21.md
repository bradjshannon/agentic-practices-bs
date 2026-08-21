# Search for the existing branch before rebuilding — a working implementation is as easy to miss as a design doc

**2026-08-21, a voice-assistant server estate, server conductor (scheduled run).**

## Symptom

A component needed a new capability: deliver one more piece of context into a downstream LLM
call, controllable by a human without a redeploy. One session investigated, confirmed the gap was
real, and spent real time deciding between two mechanisms to close it (a per-record field vs. a
global switch), then inspecting decompiled vendor bytecode to find a way to wire the chosen one
in. Two more sessions picked up that same open question later the same week.

None of them found `git branch -a` would have shown a feature branch, built a week earlier by a
different session, that already solved the identical problem — tested, with a working control
surface — and had been sitting with an explicit "human review, then merge" note in the project's
own decision log the entire time.

## What actually happened

The earlier branch and the later rebuild solved the same problem two different ways, in the same
file, and were never diffed against each other. The rebuild's own author had, days earlier in a
separate document, already written the general rule this violates — searching a repo's design
docs before designing something new — and applied it correctly to *documents*. The exact same
gap existed one layer down, in *branches*, and nothing caught it, because the check that would
have caught it (`git branch -a`, `git worktree list`, or a repo search for the feature's own name)
is not the same reflex as `grep docs/`. A design doc and a feature branch are both "prior work
that answers this," and only one of them lives in the place people remember to check.

The earlier branch had also been flagged, twice, in the project's own persistent decision log —
once by the run that built it, once by the run that reviewed the handoff — as "next concrete
action: review and merge." Both flags were read at some point and neither converted into an
actual review, because the log is long-lived and additive: new entries accumulate on top of old
ones, and an item's visibility decays with its distance from the top even though nothing marked
it resolved. A week later, the item was still technically "in the file" and functionally
invisible.

## The rule

**A negative-existence claim about a repo's own assets ("this has not been built") needs to be
checked against branches and worktrees, not just documentation.** Before starting work to build a
capability that does not exist on the current branch, run the cheap fan-out:

- `git branch -a` / `git worktree list` for a branch name matching the feature.
- A repo-wide search for the feature's own working name (the one a prior session would have used
  in a commit message), not just its problem description.
- If the project keeps a decision log or handoff file, grep IT too — not just recent entries, all
  of them. A week-old flag in a long file is still current if nothing marked it resolved.

**And the corollary for whoever is holding the decision log:** an item that says "waiting on human
review" is a liability the longer it sits, because every day it sits is another day a second
session can independently rediscover the gap and build a competing answer. If a review is
genuinely going to wait, the log entry should say how long is safe to wait before the underlying
gap gets re-solved by someone who doesn't know to look for it — not just what the next action is.

## Generalization

This is the implementation-layer twin of `search-for-the-design-doc-before-designing-2026-08-20.md`.
Same shape: a proposal to build something is implicitly a claim that nothing already does it, that
claim is cheap to check, and reasoning carefully from first principles is indistinguishable, from
the inside, from ignoring work that already exists. The new wrinkle is that "search the docs" and
"search the branches" are different reflexes, and a project with active feature-branch discipline
needs both — a thorough grep of `docs/` can pass clean while a `git branch -a` would have ended the
question in one line.
