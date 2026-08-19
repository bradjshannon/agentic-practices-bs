# An observed threshold is not a floor

**2026-08-19.** A documented failure threshold was read as a safety margin, and that reading is what
let the defect spread to a new call site.

## Symptom

A four-arm × three-replicate experiment suite was launched. Every replicate stalled for its full
40-minute timeout and wrote a **0-byte log**. The run would have spent ~8 hours and produced no
measurement. Nothing said "stuck" rather than "slow" — a stalled replicate and a slow one emit the
identical empty file.

## What actually happened

The stall was a local deadlock: `subprocess.run([...ssh...], capture_output=True)` around Windows
`ssh.exe`. Measured against the same host, the same minute, the same command:

```
capture_output=True (stdout via a pipe)   still hung when killed at 120 s
stdout=<file handle>                      9,261 bytes, rc=0, 0.6 s
```

**This was already a known bug with a shipped fix.** Five days earlier another module had hit it,
solved it by handing ssh a real file handle, and documented it thoroughly. The docstring said the
hang arrives *"once the remote command emits a couple of hundred KB"*, quoting the 218 KB case that
had been observed.

The next author read that figure, reasoned *"my output is small, a pipe is fine"*, and used a pipe.
The output was 9 KB — **4% of the quoted figure** — and it deadlocked every time.

Two false leads were measured and rejected before the cause was found, both of which *looked*
sufficient:

- **stdin inheritance.** The remote command string already ended in `</dev/null`, with a comment
  saying stdin inheritance "reads exactly like an unreachable server". That redirect protects the
  **remote** process; the local `ssh` is a different process. Adding `stdin=subprocess.DEVNULL` was
  correct and kept — and it was measured *still hanging afterwards*.
- **A stale port.** Both candidate ports answered instantly.

## The rule

**A threshold in a bug report is the value at which someone first OBSERVED the failure. It is not a
floor, and it is not a safe margin.** Nobody bisected to find where the deadlock begins; they
recorded where they happened to meet it. Writing that number into the documentation converted an
anecdote into a false boundary, and the boundary is the part readers act on.

So:

- When documenting a failure, **say what you measured, not what you infer bounds it.** "Reproduced
  at 218 KB" is a fact. "Arrives past a couple of hundred KB" is a claim about everything below it
  that nobody tested.
- When you find a second data point far from the first, **fix the inference, keep both
  observations.** Neither measurement here establishes the mechanism; both establish that a pipe is
  unsafe far below the size anyone assumed.
- **Pair the structural fix with a bound.** The file handle removes the known cause; a `timeout=`
  removes the class, turning any future stall into a readable error instead of an indefinite wait.
  Without the bound, the next variant is again indistinguishable from a slow server.
- **A rule that lives only in prose gets re-derived wrongly by the next author.** The knowledge
  existed, was well written, and did not help. What helps is a check that reads the actual call —
  here, an AST scan asserting no ssh invocation pipes stdout without a timeout. You cannot satisfy
  that by emitting a token; only by removing the pipe or adding the bound.

## Why it generalises

This is not about SSH. Any documented limit that was **observed rather than derived** invites the
same misreading: rate limits, payload sizes, timeout values, "works up to N items", "only affects
files over X MB". The number gets quoted; the "we saw it here" context does not travel with it.

The tell is a documented threshold with **no description of how it was established**. If the doc
does not say "bisected" or "the API returns 413 at exactly this value", assume it is one
observation, and that the true boundary is unknown and probably lower.

There is a companion failure worth naming, met in the same session: the same investigation
initially concluded a safety guard was missing and recommended building it. It already existed and
had shipped eight days earlier. The evidence for "missing" was a static test fixture plus a capture
**dated before the fix landed**. **Date every capture against the change you are reasoning about** —
an undated capture is a claim about a build, not about the system.
