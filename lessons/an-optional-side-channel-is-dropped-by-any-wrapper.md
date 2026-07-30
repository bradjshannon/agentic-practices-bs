# An optional side channel is dropped by any wrapper, and the loss looks like a real result

## Symptom

A 142-case test run reported **zero** instances of the thing it had just been modified to detect.
Clean sheet. The feature had been added that afternoon, unit-tested, and verified end-to-end on a
dry run. The number was wrong: the field was `null` on every single case because it had never been
populated at all.

## What actually happened

The scorer's contract with its executor was deliberately narrow — `Callable[[Case], str | None]`,
returning only which tool fired. To add the arguments a call carried without widening that
contract, the scorer read them off an **optional attribute** on the executor object:

```python
calls = getattr(executor, "tool_calls_by_case", None)
if not isinstance(calls, dict):
    return None          # "this executor has no argument channel"
```

Duck-typed, backwards compatible, and correct in isolation — the unit tests passed, because they
handed `run()` the executor directly.

The live invocation used a flag that wrapped the executor in a closure to periodically reset the
connection:

```python
def run_one(case):
    ...
    return executor(case)
return run_one          # a function. No attributes. No tool_calls_by_case.
```

`getattr` found nothing, returned `None`, and `None` was **already the legitimate encoding for "this
executor has no argument channel."** So "the probe was never wired up" and "the calls carried no
arguments" serialised to the identical value, and the identical value read as good news.

It was caught only because the analysis asserted a **positive control first** — *did this field
populate on any case at all?* — before reading any of the values:

```
POSITIVE CONTROL: results carrying non-empty actual_args: 0 of 142
  !! field never populated -- nulls below mean NOTHING
```

Without that line, "no invented arguments in 142 cases" would have shipped as a finding.

## The rule

**An optional capability read by `getattr`/duck-typing survives only as long as nothing stands
between you and the object.** Any wrapper — a decorator, a retry shim, a rate limiter, a
connection-resetting closure, a proxy added for an unrelated reason — silently removes it, with no
error at any layer.

Three things follow:

1. **Make the wrapper a proxy, not a closure.** `__getattr__` forwarding to the wrapped object costs
   four lines and makes the channel survive wrappers nobody has written yet.
2. **Never let "not measured" and "measured, found nothing" share an encoding.** If they must share
   a type, carry a separate flag that says the probe ran.
3. **Assert the probe arrived before reading what it says.** One line, at the top of the analysis:
   did this field populate anywhere? A run where it populated nowhere is a broken instrument, not a
   clean result.

## Why it generalises

This is not about test harnesses. The shape is: *a value that means "absent" is used both for
"nothing was there" and for "nothing looked."* It recurs everywhere optional instrumentation meets
composition — a tracing context lost through a thread pool, a request ID dropped by a middleware
that reconstructs the request, a feature flag read off an object that a decorator replaced, an
`Optional` metric field on a code path that never populates it.

The wrapper is always added for a good reason, by someone not thinking about your channel, and it
never errors. The only reliable defence is that the consumer refuses to interpret an all-empty
result as data.

Same run, same day, three more of the same family: a gate that skipped 100% of its inputs on a
locale-code mismatch and printed `PASS`; a caveat that existed in a page's embedded JSON while the
template never referenced it; and a flake rate computed across replicates pooled on axes nobody
recorded. **Four false greens in one session, every one produced by tooling built that session to
prevent exactly this.** Writing the check does not exempt you from checking the check.
