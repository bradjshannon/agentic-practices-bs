# A mirror copy surviving is luck, not a safety net — 2026-08-24

## What happened

A conductor run (2026-08-23, server domain) did real work, wrote a proper wind-down: a compact
session file with its judgment, and a `needs-you.md` delta summarizing four shipped fixes. Both
were current enough to get synced into a downstream mirror in a *different* repository (an ops
status page pulls a copy of `needs-you.md` into its own repo and pushes that copy). The sync
succeeded and was pushed.

The originals were not. `git log` on the authority repo shows no 2026-08-23 commit touching
either the session file or `needs-you.md` at all — it jumps straight from 2026-08-22 to the next
run, 2026-08-24. The wind-down skill produced correct content and (presumably) ran `git push`, but
the push never landed, and nothing in the run's own output said so.

The next conductor found the gap by trying to read the missing session file — and only recovered
the content because the downstream mirror happened to still have it. The mirror's copy is a
*summary for a human*, not the original: gone with it were the run's actual judgment (what it was
uncertain about, what it considered and rejected, corrections to its own reasoning) — the exact
material the wind-down procedure exists to preserve.

## The wrong read

"It's fine, the content survived via the sync." **No** — it survived *this once*, by accident, because
a downstream consumer happened to keep its own copy and that copy happened to get pushed
correctly. The next unpushed wind-down will not be so lucky: most artifacts have no downstream
mirror, and even this one only preserved the *summary*, not the *session file* the summary was
distilled from.

## The rule

**A `git push` that returns success is a claim, not a receipt.** After any wind-down (or any
"this must survive to the next run" write), verify the push landed in the artifact's own repo by
reading it back from the remote — `git log origin/<branch> -- <path>`, or a fresh `git show
origin/<branch>:<path>` — not by trusting the command's exit code, and not by trusting that *some*
copy of the content exists somewhere. This is the exact same §6a shape ("verify the postcondition,
not the exit code") applied to git instead of to a database write or a deploy — the mechanism that
can silently fail is different, the discipline that catches it is identical.

## Why it generalises

Any system with a designated "durable carrier" (a session file, a decision log, a config-of-record)
is vulnerable to this the moment something *downstream* of that carrier also happens to retain the
information — because a human (or the next agent) checking "did this survive?" will find a
plausible-looking answer in the downstream copy and stop looking, never noticing the authority
itself is empty. The fix is not "sync harder" (see `single-authority-not-mirrored-copies-2026-08-01.md`
for why mirroring facts doesn't fix drift) — it's confirming the *one* place designated as durable
actually received the write, every time, because nothing else is guaranteed to be there next time.
