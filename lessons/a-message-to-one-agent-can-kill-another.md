# A message sent to one agent can cancel a different one — check for uncommitted work before concluding it produced nothing

## Symptom

A subagent that had been running for over an hour never sent a completion notification and never
committed. Its branch tip was unchanged. The natural reading — "it died early, or it accomplished
nothing" — was wrong in a way that would have destroyed a finished piece of work.

## What actually happened

The agent had finished. Six files sat fully edited in the shared working tree: a new store module
with a required field and a load-bearing timestamp, two test files, a contract document, and a
changelog entry — coherent, internally consistent, complete. It had simply never reached its commit.

The trigger was almost certainly a `SendMessage` the coordinator sent to a **different**
concurrently-running agent. Sending a message can cancel a running agent as a side effect, and the
victim is not necessarily the recipient.

The recovery was cheap because the work was on disk: run its test suite (green, +9 tests), run the
linter it never reached (7 line-length violations, mechanical), re-run the two affected test files
after the wrapping to prove the cosmetic fix broke nothing, then commit with the authorship stated
in the message.

## The rule

**A silent agent is a claim about a notification, not about a working tree. Look at the tree.**

Before concluding that an agent produced nothing:

1. `git status` the repo it was working in. Uncommitted work in files matching its brief is its
   output, whatever the notification said.
2. If work is there, **recover it — do not revert it and do not re-dispatch.** Re-dispatching pays
   for the same work twice and risks a second agent fighting the first's leftovers.
3. Run whatever gate the agent did not reach. A lot that dies before its lint pass leaves real but
   unpolished work; finish it rather than discarding it.
4. **Attribute it in the commit message.** The next person reading `git log` should not believe the
   coordinator wrote it, and the fact that agents can be cancelled this way is worth recording where
   someone will find it.

And the prevention: **the absence of a completion notification is the signal that an agent may still
be live.** A human saying "it stopped" is not evidence it stopped; neither is a long silence. Never
revert or clean up working-tree files that a possibly-live agent authored.

## Why it generalises

This is the shared-mutable-state problem with an unusually bad failure surface. Two agents on one
tree is a known hazard, normally discussed as an *index* race — one agent's staged files landing in
another's commit. This is the mirror image: the work is perfectly intact and simply unclaimed, and
every cheap signal (no notification, unchanged branch tip, no report) points at "nothing happened."

The general shape: **when a process is cancelled by something other than itself, its output survives
in whatever medium it had already written to, and none of its status channels will say so.** The
status channel and the artifact have different lifetimes, so trust the artifact. Any orchestration
system where one task's control operations can affect another task inherits this, regardless of what
the tasks are.
