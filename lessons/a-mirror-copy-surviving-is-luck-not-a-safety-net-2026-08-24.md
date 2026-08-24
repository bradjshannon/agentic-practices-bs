# A stale local git clone reads as "the other run's work vanished" — 2026-08-24

**CORRECTION (same day, ~30 minutes later): this file originally told a different, wrong story
— that a wind-down push had silently failed and a downstream mirror copy was the only reason the
content survived. That premise was false, discovered before it reached anyone: the "missing"
commit was on `origin/main` all along, and the mirror was never load-bearing. Rewritten below with
what actually happened.**

## What happened

A conductor run (2026-08-24) went looking for whether a prior run (2026-08-23) had left a session
file in the authority repo. Its local clone — pulled once, early in the current run — showed no
2026-08-23 commit at all under the relevant path: `git log` jumped straight from 2026-08-22 to the
current run's own work. It concluded the prior run's wind-down push had silently failed, spent
real effort "recovering" the content from a downstream mirror copy in a different repo, wrote a
whole recovery narrative into a new session file and into the shared handoff doc, and (this file,
originally) published a lesson about mirror copies as an accidental safety net.

**All of it was wrong.** When the run's own unrelated push was rejected (non-fast-forward) and it
fetched to resolve the conflict, `origin/main` turned out to already contain the "missing" commit
— pushed by the 2026-08-23 run itself, on time, correctly authored. It had simply been merged into
`main` later than usual by an unrelated concurrent process (a different conductor domain's own
wind-down, picking up and merging in a commit that had been sitting on a branch). The local clone
that reported it missing was stale relative to `origin/main` at the moment of the check — the
earlier `pull` in the same run predated a large batch of upstream commits, and nothing re-fetched
before the "it's missing" conclusion was drawn.

## The wrong read, and why it happened

"`git log` shows nothing since 2026-08-22, therefore nothing since 2026-08-22 reached the remote."
That conflates **"absent from my local clone"** with **"absent from the remote"** — the same
conflation this project's own debugging guidance already names for grep searches ("a negative
literal string search closes one search path, not the question") and for file reads ("clean ≠
current" — a shared clone can sit on an old commit with a clean status). A `git log` on a *local*
ref is exactly as vulnerable as a working-tree read: it answers "what does my copy currently show,"
not "what is actually on the remote right now."

The false conclusion then compounded: instead of `git fetch` before concluding, the run reasoned
forward from the (stale) negative and built an entire incident narrative — a "recovery," new
priming content, a published lesson — on top of it. Confirming was one command
(`git fetch && git log origin/main -- <path>`) away the whole time.

## The rule

**Before concluding a commit, file, or piece of work is missing from a shared repository, `git
fetch` fresh and check against `origin/<branch>` directly — never a local ref that was last synced
earlier in the same session.** A `pull` from twenty minutes ago is already a snapshot, not a live
view, on any repo other agents or processes are also writing to. Treat "missing from `git log`" the
same way this project already treats "missing from a directory listing" or "missing from a `grep`":
a claim about the population you actually checked, not about reality.

## Why it generalises

Any multi-agent or multi-process environment where several actors write to the same remote makes a
local clone's freshness an unstated, decaying assumption — and the decay is invisible until
something (here, an unrelated push rejection) forces a fetch. The specific trap is that a *negative*
git-log result reads as authoritative because git itself gives no visible warning that the local
ref might be behind; contrast a merge conflict or a rejected push, both of which are loud. Before
building anything — a diagnosis, a recovery, a lesson — on top of "I don't see it," re-derive that
absence against the freshest possible view of the remote.
