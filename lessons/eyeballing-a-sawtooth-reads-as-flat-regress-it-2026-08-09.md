# A sawtooth on a rising trend reads as "flat" to a human, and a model that fits with no free parameters is not thereby correct — 2026-08-09

## Symptom

A capture-throughput investigation ran for two days on a model that predicted two independent
devices with **no fitted parameters** — 16.0% predicted vs 17.2% measured on one, 24.6% vs 24.6% on
the other. That accuracy is why nobody re-derived it. Two headline results were then reported to the
operator from measurements taken under it. **Both were wrong.**

## What actually happened

Two distinct failures, and they compounded.

**1. The parameter-free fit was a three-way cancellation, not a law.** The measured quantity carried
three independent errors that happened to nearly annul: **+9.7%** (the monotonic clock ran fast in
the container), **−10.4%** (the metric averaged all frame types, while the quantity of interest was
one type's cycle), **−3%** (median reported where the arithmetic wanted a mean). Net: 1.4% apart, by
luck. When one experimental variable doubled, the second term moved, the cancellation broke, and the
model's predictions diverged from reality — which is when anyone looked.

**2. The confirming measurement was a transient, and eyeballing could not see it.** A "loss is ~0%"
verdict came from a 250 s window. The backlog series over the same window:

```
1.15  1.97  2.41  1.20  2.73  3.65  2.12  3.31  3.71  2.74  4.19  4.90
```

Regressed, that is **+0.0267 units/s** — a clear rise, saturating the buffer at ~360 s. Read by eye
it looks flat, because every third point *drops*. A reader scanning for monotonicity sees the dips
and concludes "no trend". The window ended 110 s before the effect it was looking for could appear.

## The rules

**Regress a series; never eyeball it for a trend.** Human trend-detection tests for monotonicity,
and any sawtooth defeats it. This costs one line of code and it is the difference between a verdict
and a guess. If you find yourself writing "looks flat" or "no clear trend" about a printed series,
you have not measured it.

**A parameter-free fit is evidence, not proof — and a *suspiciously* good one deserves more
scrutiny, not less.** Ask what would have to be true for it to fit by accident. Independent errors
that cancel are not exotic: they are common whenever several corrections of similar magnitude and
opposite sign act on the same quantity. The tell is that the fit holds at one operating point and
degrades when any variable moves — so **test a model at a second operating point before trusting it,
especially when it was never fitted.**

**An analyser must refuse a verdict its window cannot support.** If the phenomenon needs
`buffer_depth / observed_slope` seconds to appear, a shorter window can only produce a transient.
That is a computable precondition, so make the bad state unrepresentable: emit the required window
length instead of a number. A guard here would have caught both failures above; a reminder would
have caught neither.

## Why it generalises

None of this is domain-specific. The pattern is: **a derived metric that bundles several
corrections can be accurate for the wrong reasons, and a measurement window chosen by convenience
rather than by the model's own timescale will confirm whatever it was short enough to miss.** Both
survive review indefinitely, because both produce internally consistent, plausible numbers — there
is no error to notice. They are found only by re-deriving from raw data with the suspect
intermediate removed, which is worth doing once for any number a project has been steering by.
