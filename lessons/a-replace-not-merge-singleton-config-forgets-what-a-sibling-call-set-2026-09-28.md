# A replace-not-merge singleton config forgets what a sibling call set

**Symptom:** two independently-branched lots each added a new kwarg to the same `configure()`-
style call in a shared file. Both lots' own test suites passed in isolation. Merged together, a
real regression appeared — but only in tests that ran late enough in the file to be affected —
because a *third, unrelated* call to the same function, elsewhere in the file, didn't repeat
either new kwarg and silently reset both to their defaults.

**What actually happened:** the file had FOUR sequential calls to one `configure(...)` function
(a module-global singleton setter, documented as "each call fully replaces the previous state, it
never merges"), because different pieces of config became available at different points while the
file loaded. Two lots (call them A and B) each correctly updated the call where THEIR OWN new
kwarg first became relevant, and each correctly repeated every pre-existing kwarg at that call
site per the documented contract. Neither lot's author knew about a LATER, unrelated call further
down the file (added by a third, earlier lot, for a third kwarg) — so that later call didn't
repeat A's or B's kwargs, and reverted both to defaults. The bug was invisible to a `git merge`:
there was no textual conflict, because A and B touched different lines than the reverting call.

**The rule:** when N call sites to a replace-semantics singleton setter must each repeat the full,
accumulated state, "does this diff apply cleanly" is not the check — "does every OTHER call site
to the same setter still repeat what this change added" is. Grep every call site of the function
before considering a kwarg addition done, not just the one you're editing. A test failure in
isolation-of-the-two-new-things is not sufficient evidence; run the SPECIFIC tests that exercise
state set by the earliest call, since those are the ones a later un-updated call can silently
clobber.

**Why it generalises:** this shape — a singleton configured by multiple sequential calls because
different config becomes available at different times, documented as "replace, don't merge" —
recurs anywhere a module needs progressive initialization (DI containers configured in phases,
Django-style settings patched incrementally, a test fixture's `setUp` calling a shared `configure`
more than once). Two independently-authored diffs to DIFFERENT call sites of the same function can
each be individually correct and still combine into a regression with zero textual conflict,
because the failure mode isn't "these two edits disagree" — it's "a THIRD, untouched call forgot
what either of them added." A merge tool cannot catch this; only enumerating every call site can.
