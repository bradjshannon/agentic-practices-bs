# When a detector fires on your own test traffic, it is measuring you

**2026-08-17. Cost: a detector that would have shipped permanently red, plus one full wrong pass
before the corpus problem was visible.**

## Symptom

A new monitor looked for a real defect — an appliance changing spoken language mid-conversation
when nobody asked it to. The raw signal was abundant: 36 of 499 sessions over 14 days contained a
language change. After four rounds of narrowing, 22 candidates survived, and they looked
convincing: a consistent drift toward one language, refusal-shaped replies, plausible root cause.

Every single one was our own automated test harness. Several "sessions" had 400+ user turns.

## What actually happened

The system under test was also the system generating most of its own traffic. The harness
deliberately exercised the exact behaviour the detector was built to find — cycling through
languages on purpose — so the defect's fingerprint and the test suite's fingerprint were identical.

Two further traps sat inside the fix:

1. **The obvious exclusions were the wrong ones.** The harness could not be excluded by device
   identity, because it drives *real* device identifiers. It could not be excluded by volume alone
   without inventing a threshold. What worked was set membership: a session whose utterances are all
   drawn from the test catalog is the test catalog running.

2. **Identifying traffic and scoring against it want different corpora.** The catalog loader hides
   unreviewed machine-translated cases behind a `reviewed: false` flag — correct for scoring, since
   nobody has vetted them. But the harness *speaks* those unreviewed cases. Loading the corpus the
   scoring way matched 23% of harness turns and classified **none** of the 22 candidates as harness.
   Loading it with the unreviewed sets included matched the same sessions at 100%.

Two adjacent findings had the same shape and were not this defect at all: they were untranslated
diagnostic strings belonging to a *different* monitor. Excluding them by pattern did not converge —
each pattern caught one string and missed the next — so the exclusion had to be structural
("a reply in a language the user never used belongs to the other detector"), not textual.

## The rule

**Before trusting any detector's findings, ask what fraction of the observed population you
generated yourself — and answer it with a measurement, not an impression.**

Concretely:

- **State the real-traffic denominator in every result.** "Zero findings" and "zero findings across
  505 real user turns" are different claims, and only the second one is evidence. A window with no
  real traffic must report *could not run*, never *pass*.
- **Separate synthetic from organic by set membership against the thing that generates it**, not by
  identity or volume. Generators reuse real identities; thresholds need constants nobody can defend.
- **A corpus loaded for identification is not the same corpus loaded for evaluation.** Quality gates
  that correctly hide unvetted data from scoring will also hide it from recognition. Ask which job
  you are doing before you reuse a loader.
- **Build the discriminator against live data, not at the desk.** All four exclusions here were
  forced by observation; a desk design would have shipped at roughly six times its true finding
  count, and every one of those findings would have read as plausible.

## Why it generalises

Any team mature enough to have automated tests running against a shared environment has this
problem, and it gets worse exactly as testing improves. The better the test suite, the more it
exercises rare and dangerous behaviour — which is precisely the behaviour anomaly detection looks
for. Synthetic traffic therefore concentrates in the tail the detector cares about, not uniformly.

The failure is quiet in both directions. Ship without the split and the detector is permanently red,
so it gets ignored, and a real finding arrives in a channel nobody reads. Ship with an over-broad
split and it is permanently green, having quietly excluded the real cases too. Neither shows up as
an error; both show up as a number that looks reasonable.

The generalisable habit is small: **a count is not a result until it is paired with the size and
provenance of the population it was counted over.**
