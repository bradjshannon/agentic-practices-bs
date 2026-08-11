# A clean `git log` with a dirty `git status` is a lost handoff — 2026-08-03

## Symptom

A conductor run wound down cleanly by its own account — operator-directed, at a stated context
percentage, with a session file describing real, verified work. The next run's preflight showed
nothing wrong: `git log` on the relevant repo ended exactly where the session file said it would.

Priming the next run anyway (session-continuity step: list the most recent files, read the most
recent one) turned up two things that shouldn't have been there: the session file itself existed
only as an **untracked file** — never `git add`ed, let alone committed — and a second file the same
session had edited (a live decision-tracking doc) sat as an **uncommitted working-tree diff**. Both
had been sitting exactly like that since the moment the prior session ended.

## What actually happened

The prior run did the real work, wrote the real handoff to disk, and then the process ended —
whether by running out of context, a kill, or simply not reaching its own final `git add && commit
&& push` step — before that last write reached git. Nothing about this is visible from `git log`,
because `git log` only shows what a commit recorded; it has no way to show you a file that was
never staged. The repo looked exactly as clean as a repo that never had unfinished business.

**The failure has two independent copies of the same shape**, which is what made it easy to miss
once and catch the second time only by accident: the same uncommitted content existed in two
different worktrees (one canonical, one a mirror kept in sync for a different consumer), because
the session had edited both and committed neither.

## The rule

**A "the last run wound down cleanly" read that comes only from `git log` is not evidence of
anything — it is the same read a lost handoff produces.** Before trusting that a predecessor's
work actually reached the repo, run `git status` (or equivalently, look for untracked files in the
directory the session-file convention names) on every repo the session touched, not just the one
you're about to write to. A clean log and a dirty status is the specific, distinguishable signature
of "the work happened, the commit didn't" — and it looks, from the log alone, identical to "nothing
was in flight."

## Why it generalises

This is not specific to conductor sessions or to git. Any workflow that treats "the artifact reads
correctly" as proof of "the artifact was durably recorded" has the same gap: a write to a staging
area, a buffer, a draft, or a local disk is real work that can vanish at the exact moment between
"done" and "persisted," and the check that would catch it (is there uncommitted/unstaged/unflushed
state sitting here) is a different check from the one that confirms the content is right. Checking
only the latter and inferring the former is how a genuinely finished piece of work gets silently
lost one layer before the point everyone was checking.

**The corollary for the agent that finds this:** recovering it is not "discovering new work" — it
is completing a handoff that already happened once. Commit it as a recovery of the prior session's
intent, not as a fresh finding, and say so explicitly in the new commit message, so nobody credits
the recovering session with work it did not do the analysis for.
