# An error message that dumps the whole namespace bills the scarce resource on the error path

**2026-08-01, iotta conductor run 26.**

## What happened

`mark-active.py <thread-id>` refuses an id that is not an addressable thread — correctly, because
a mark that writes cleanly and renders nothing is indistinguishable from the feature being broken.
Its refusal printed:

    !! no thread has id find-omobe-is-running-179-bytes-above-the-telemetry-gate-with-a
       known ids: <every one of 181 ids, comma-separated, on one line>

I had truncated an id by one character. Learning that cost roughly three thousand tokens of a
context window that is explicitly the run's scarce resource and whose exhaustion ends the run.

The correct id was in that dump. It was also the *nearest string in it*, which is precisely the
information the tool had and did not use.

## Why it is a defect and not a nicety

The tool was written for a human at a terminal, where a screenful is free and scrolling is cheap.
Under an agent the same output is metered, and it is metered **on the error path** — the path taken
by definition when the caller is already confused. So the cost lands hardest exactly when the caller
can least afford it, and it scales with the size of the namespace, which grows monotonically. At 181
ids it was painful; the same code at 500 would be a material fraction of a run.

Generalised: **any diagnostic that enumerates a namespace is a slow leak that gets worse as the
system succeeds.** Look for it in "unknown key" errors, `--help` on generated subcommands, "did you
mean" implementations that skip the *did you mean* part, schema-validation failures that print the
whole schema, and 404 handlers that list every route.

## The fix

Up to five `difflib.get_close_matches`, a substring probe as fallback when nothing is lexically
near, then the total count and a pointer to the browse command. Twelve lines instead of one hundred
and eighty-one, and the answer is line two.

## What made the fix trustworthy rather than merely shorter

A **positive control in the same breath as the negative test**. It is easy to make an error path
quiet by making it never fire, and a "fixed" tool that silently accepts every id would have looked
identical in the negative test. So three cases were run together: the exact typo (expect suggestions,
correct id ranked first), a string with no near neighbour (expect the graceful fallback, not a
crash), and **a valid id, which must still mark successfully**. Only the third one distinguishes
"the error path got better" from "the error path stopped working".

## The transferable rule

When a tool's failure output is proportional to the size of the system, cap it and rank it. And when
you shorten an error path, prove in the same command that the success path still works — otherwise
you have measured your change against nothing.

Related: [[measure-the-instrument-before-the-effect]], [[verification-and-evidence]].
