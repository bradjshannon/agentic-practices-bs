# A "flat" reading from an unvalidated instrument is not a null result

**Symptom.** A purpose-built instrument was added to settle whether a measured quantity
stepped at a known boundary. It reported *flat* — a clean, publishable answer that would
have killed the hypothesis. It was wrong three times in a row, for three different reasons,
and each time "flat" was indistinguishable from a real null.

**What actually happened.** Over one evening, the same instrument failed three ways:

1. **No wall-clock anchor.** Buckets carried only relative `start_s_ago` offsets, so any
   consumer reconciling them against a stored record set had to supply its own "now" — and
   any skew displaced every sample by exactly that skew (~20-26 s, the same order as the
   signal being hunted).
2. **Anchor fixed, axis still wrong.** Placement was still computed from an age measured in
   `perf_counter` units and *labelled* from a wall clock — so the axis was stretched rather
   than shifted, smearing samples across ~2 buckets and washing out the feature.
3. **The clock itself was wrong.** `perf_counter` over-reported by ~7-13% in that
   container. The first attempt to measure this was **circular** — it compared
   `perf_counter` against `time.sleep`, both of which use `CLOCK_MONOTONIC`, so it could
   not have failed. It took bracketing against an independent NTP-disciplined host clock to
   get a real number.

The defects were found by comparing the instrument's output against an **independent
oracle** — a stored ring of the same events, written by a different code path with a
different clock. Never by reading the instrument more carefully.

**The rule.**

- **Before believing a null from a new instrument, cross-check it against an independent
  record of the same events.** A defect that shifts, stretches or smears the axis produces
  *flatness*, which is exactly what a true null looks like.
- **Express the cross-check as an invariant a machine can assert**, not a manual comparison.
  The one that caught both versions here: *per-bucket `records / frames` must never exceed
  the known batch size*. One assertion; it fails loudly on any misalignment.
- **A clock cannot validate itself.** Comparing two APIs backed by the same underlying clock
  source is a control contaminated identically to the treatment. Bracket against a source
  with a genuinely different discipline.
- **Distinguish a bias from a step.** A uniform scale error (a fast clock) shifts every
  absolute number and can never manufacture or erase a transition — so it invalidates
  cross-instrument *comparisons* while leaving within-instrument *shape* intact. Saying
  which one you have prevents discarding good data.

**Why it generalises.** Any derived view — a rollup, a time series, a dashboard, a metric —
is a second implementation of something an authoritative store already knows. That
duplication is the opportunity: the store is the oracle, and one invariant asserted between
them converts a class of silent instrument failure into a loud test failure. Without it, the
instrument's most dangerous output is not an error but a plausible answer.
