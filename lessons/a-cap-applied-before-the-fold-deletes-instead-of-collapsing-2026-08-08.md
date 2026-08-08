# A cap applied before the fold deletes instead of collapsing

## Symptom

A status page showed a growing fraction of open items **nowhere at all** — not in the list, not in
the collapsed catch-all section, not in the generated markdown export. Measured at three points over
two weeks: 33 of 35 absent, then 60 of 76, then 62 of 84. The page rendered cleanly and reported no
error. Items filed against it could not be actioned or closed by the human, because they had no
presence on the surface at which actioning happens.

## What actually happened

The renderer had a deliberate two-stage design: partition items into an *actionable* set rendered
prominently, and a *rest* set folded into one collapsed summary section. Folding-into-a-summary is a
perfectly good answer to "too many items."

The defect was **ordering**. A `limit` parameter capped the rest bucket *before* the fold ran:

```
rest = fetch_rest(limit=10)     # cap applied here
feed = partition_and_fold(rest) # fold applied to the survivors only
```

So the cap did not select what to summarise — it selected what to *exist*. Item 11 onward was never
handed to the folder, so it was not collapsed, it was **dropped**. And because nothing ages an item
out of "open" except explicit resolution, the bucket only grew, meaning a fixed cap against a
growing population silently deleted an increasing share. The drift series above is that geometry,
not a series of separate regressions.

The fix was one constant. Finding it required reading the call order, because every individual
component was behaving correctly.

## The rule

**A truncation and a summarisation look identical in the code and are opposite in effect. Check
which side of the fold your cap is on.**

A cap *after* the aggregation step is a display decision: everything is still represented, some of
it compactly. A cap *before* the aggregation step is a deletion, wearing the vocabulary of a display
decision — the variable is still called `limit`, the intent in the author's head was still "don't
render a thousand rows," and the reviewer reads it as bounded output rather than bounded existence.

Corollary for the failure's *invisibility*: a bounded-output cap should be paired with a rendered
count of what it elided ("showing 10 of 84"). Silent truncation is what let this run for weeks; the
absent items produced no error, no warning, and no gap in the page.

## Why it generalises

The same inversion appears wherever a pipeline has a narrowing step and a summarising step and the
order is not enforced:

- `LIMIT` in a subquery that a downstream `GROUP BY` was meant to aggregate over — the groups are
  computed from a sample, and the result is a plausible wrong number rather than an error.
- A log shipper capping lines per batch before the aggregator computes rates.
- Pagination applied before a filter rather than after, so page 2 is not "the next 20 matches."
- Any `head -n` upstream of a `sort`.

In every case the tell is the same: the cap's *name* describes an output constraint while its
*position* makes it an input constraint. Ask "does this bound what is shown, or what is considered?"
— and if the answer is "considered," either move it or surface the elision count.
