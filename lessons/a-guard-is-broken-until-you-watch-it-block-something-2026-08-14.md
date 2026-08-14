# A guard is broken until you have watched it block something

**Date:** 2026-08-14 · **Domain:** agent tooling, git hooks, CI checks · **Cost:** would have been
a silent recurrence of the exact incident the guard was written to prevent

## Symptom

A `pre-rebase` git hook had been written specifically to stop a destructive incident: an agent
running `git rebase --autostash` on a dirty tree and destroying another session's uncommitted work.
The hook's own docstring stated it covered `--autostash`. It was staged, reviewed, and approved for
installation across three repositories.

It did not work. Installed as-is, the original incident would have sailed straight through.

## What actually happened

**Git performs the autostash *before* invoking the `pre-rebase` hook.** So by the time the hook ran
and checked "is the working tree dirty?", the tree was **clean** — git had just stashed everything.
The check answered honestly and answered "no problem here."

The guard was not subtly miscalibrated. On the one input it existed to catch, it was **inverted**.

This surfaced only because installation was gated on a positive control: reproduce the bad thing in
a scratch repo and *watch the hook refuse it*. It didn't refuse. The fix was to also detect git's
`rebase-merge/autostash` / `rebase-apply/autostash` marker files, which do exist at hook time
precisely because the stash already happened.

## The rule

**Do not count a guard as protection until you have observed it block the specific thing it was
built for, and allow a legitimate near-neighbour.** Both directions, on the real mechanism, before
you rely on it.

Corollaries:

- **A guard's own documentation is not evidence.** This one's docstring asserted the coverage it
  did not have. Docstrings are written from intent; behaviour comes from the runtime.
- **Review does not substitute for execution.** The hook was read by multiple parties and the
  ordering bug is invisible on the page — it lives in git's execution order, not in the code.
- **The dangerous failure is the guard that is inverted on exactly its target case.** A guard that
  fails broadly gets noticed. One that works everywhere except its reason for existing is
  indistinguishable from a working guard right up until the incident it was supposed to prevent.

## Why it generalises

Any check that runs inside a lifecycle you do not control — a git hook, a CI step, a framework
callback, a database trigger — observes state *after* whatever the host did first. Your mental
model of "what the world looks like when my code runs" is an assumption about someone else's
ordering, and it is the assumption least likely to be written down anywhere.

The same shape, from the same estate on the same day: a shell script's success path crashed because
`grep | wc -l` exits non-zero when grep finds zero matches, and `set -o pipefail` killed the script
before it wrote its completion marker. Every run correctly did the work and then reported failure.
Nobody noticed for weeks because "did the work" and "reported success" were never compared.

And a third: a hook designed to force agents to verify background work told them to run a specific
census command. That command belonged to a **different subsystem** and returned "nothing found"
even with several tasks genuinely running — so the guard reliably steered its user toward a false
negative, while looking like diligence.

**Generalised: a control's proxy, its documentation, and its remedy text are three separate things
that can each be wrong independently of the control's intent.** Only execution tests all three at
once.

## Related

- `mechanisms/runtime-flag-must-be-readable-from-outside.md`
- `lessons/verification-and-evidence.md`
