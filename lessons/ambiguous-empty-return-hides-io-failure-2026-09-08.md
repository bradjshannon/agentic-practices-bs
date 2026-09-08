# An "empty result" return that can mean either "genuinely nothing" or "read failed" forces every caller to guess — and eventually one guesses wrong under load

## Symptom

A device's SD-archive drain loop went into a hot retry storm — dozens of retries landing within
the same one-second window — once its SD card started faulting at the block level. The retry code
already had a defensive heuristic (`cursor < next_seq`) specifically because the underlying read
function's return value gave it no other way to tell "the backlog is genuinely empty" apart from
"the read just failed." The heuristic caught the failure correctly, but nothing bounded the retry
rate once it did, so a real hardware fault turned into unbounded heap churn (allocate/free on every
failed attempt) piled onto an already-tight memory budget.

## What actually happened

The read function's return type had a `records` list, a cursor, and a `gap` flag — none of which
distinguished "I/O error, nothing read" from "no error, backlog is drained." The implementation
*logged* failures internally but returned the ordinary empty-result shape regardless, so from the
caller's perspective the two cases were byte-identical. The caller had already worked around this
once (the cursor-comparison heuristic); the actual defect — no way to represent failure in the
return value at all — was still there, and a second consumer of the same underlying pattern didn't
get the workaround, or the workaround wasn't suficient to also bound retry *rate*, not just detect
the failure.

## The rule

**When a read/drain function can fail at the I/O layer, its return type must make that failure
structurally impossible to conflate with a valid "nothing here" result** — not a boolean field a
caller can construct-and-ignore, but something the type system (or, in a language without
exceptions, a `[[nodiscard]]`-style enforced return) makes a caller actually handle. If a caller
has already grown a heuristic to work around an ambiguous return, that heuristic is itself the
signal that the return type is wrong, not evidence the gap is already handled.

## Why it generalises

Any "peek the next batch" or "read from a spool/queue/log" API that can fail at the storage layer
has this shape available to it. The fix is cheap early (a status enum alongside the result) and
expensive late (every caller has already grown its own ad-hoc failure-inference heuristic, and a
new caller that doesn't know to add one gets the storm this incident describes). Audit sibling
consumers of the same underlying store for the identical bare-empty-return pattern before assuming
one fix covers the whole surface.
