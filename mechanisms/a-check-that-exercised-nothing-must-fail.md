# A check that exercised nothing must fail, not pass

**Class:** fail-closed guard, inside the checking tool itself.
**Cost:** ~6 lines. **Detects:** a filter, join, or selector that silently matched nothing.

## What it does

Any tool that answers "did anything go wrong?" over a set of inputs counts what it actually
evaluated, and **raises rather than reporting a clean result when that count is zero.**

```python
class NoCoverage(RuntimeError):
    """The gate ran but exercised no case, so its result means nothing."""

...
if evaluated == 0:
    raise NoCoverage(f"0 of {len(cases)} cases were evaluated; nothing was tested")
```

Exit code for "could not run" must differ from both "passed" and "failed" — the caller has to be
able to tell a broken instrument from a verdict.

## Why it exists

A gate written to check 541 phrases against a rule set printed:

```
PASS — no must-not utterance was recognised as a dispatchable operation.
```

It had evaluated **zero** of them. The catalogue tagged cases `en-US`; the rule set keyed on `en`.
Every case was filtered out by a locale-code mismatch, and a run that tested nothing produced the
same output as a run that tested everything and found nothing wrong.

A `WARNING` line *was* emitted saying 541 were skipped. It did not help: the headline still said
PASS, and the headline is what gets read and quoted. **A warning that contradicts the verdict loses
to the verdict.** The guard has to change the outcome, not annotate it.

## What it cannot detect

- **Partial coverage.** 540 of 541 skipped still passes this guard. If the filtered fraction
  matters, log evaluated-vs-total and threshold on it.
- **Wrong-but-nonzero inputs** — evaluating the wrong 541 things.
- **A check whose assertion is vacuous** on inputs it did reach. This proves the pipeline moved
  data, not that the assertion could ever fail. If you cannot say what would make your check fail,
  you wrote an assertion, not a test.

## Where else it applies

Any tool with a selector between the input and the verdict: linters with path globs, migrations
with `WHERE` clauses, a security scan with an include list, a report over a filtered query. The
tell is a summary line whose value is computed from a set that a config change can silently empty.
