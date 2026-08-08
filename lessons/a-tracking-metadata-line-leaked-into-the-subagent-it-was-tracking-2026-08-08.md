# A tracking-metadata line leaked into the subagent it was tracking

**2026-08-08.** `estimate_tracker.py` (mechanism: `mechanisms/scripts/estimate_tracker.py`)
requires every `Agent` dispatch to carry an `ESTIMATE: <duration>` line in its prompt, so a
Stop-hook can later reconcile the estimate against the harness's own measured `duration_ms`.
The `PreToolUse` hook enforced the line's presence, recorded it, and then allowed the dispatch
— but the `allow()` path was a bare `sys.exit(0)`, so the unmodified prompt, ESTIMATE line
included, reached the subagent verbatim.

## Why this was wrong

The estimate is dispatcher-authored bookkeeping — a prediction of how long the *subagent* will
take, made by the agent doing the dispatching, before the subagent has seen the task. It has no
business being part of the subagent's own instructions. It is not the subagent's estimate of
itself, and the subagent has no way to know that.

**A subagent, mid-task, read that number as its own budget and self-terminated against it.** A
card-triage sweep stopped at 13 of 89 cards after using ~32 of an allotted ~120 minutes, and
reported "ran out of time" — a false description of its own state, produced by treating tracking
metadata as an instruction. Aggregate data from 60 reconciled dispatches (median
actual/estimate ratio 0.41 — agents typically finish in under half their given estimate) shows
this was the *first* observed instance of an agent visibly racing the number, not a
demonstrated recurring pattern. The fix is preventive, not a fix for something proven to
recur — but a single instance of a dispatcher's private bookkeeping directly distorting a
worker's behavior is enough to justify closing the leak regardless of frequency.

## The fix, and why it's the RIGHT fix, not a workaround

`PreToolUse` hooks can return `hookSpecificOutput.updatedInput` to rewrite a tool call's
parameters before it executes — the same hook file's own `deny()` path already used the
sibling capability (`permissionDecision: "deny"`) two lines above the unused `allow()`. The fix
adds `allow_redacted()`: strip the `ESTIMATE:` line from `tool_input.prompt` via `updatedInput`
before the call proceeds, while still recording the *original* prompt's estimate for the
tracking dataset. The subagent never sees the line; the tracking data is unaffected, since the
recording happens before redaction.

**The instinct to reach for "there's no out-of-band channel, so the leak is unavoidable" was
wrong**, and worth naming as its own trap: the channel already existed in the same file, for
the opposite branch (`deny`), and simply hadn't been extended to the `allow` branch. Before
concluding a tool's parameter surface has no side channel for metadata, check whether the SAME
hook already uses one for a different outcome of the same decision.

## The generalizable rule

**Any hook that inspects a tool call's input for bookkeeping purposes must not let where it
extracts data from be inseparable from what the tool call actually receives**, when the two
audiences (the dispatcher's own tracking, and the thing being dispatched) are different. If a
`PreToolUse` hook can rewrite what a tool receives, prefer stripping tracking-only content from
the payload over accepting that "the target sees everything the wrapper does."

## See also

`mechanisms/scripts/estimate_tracker.py` for the mechanism; `commit_verify.py` in the same
directory shows the same principle from a different angle (fail loudly rather than compose a
plausible-looking success from unobserved state).
