# An expectation no system can satisfy is not a failing test

## Symptom

A newly-built test suite runs for the first time and scores 58%. The instinct is to treat the
failures as findings — a defect list, a red dashboard, an afternoon of triage. Someone starts fixing
the system.

## What actually happened

First live run of a 246-case suite against a real server: **184 passed, 132 failed.**

Before reporting it, we checked each failing expectation against the list of things the system could
*possibly* do — the live tool manifest. **70 of the 132 named something that did not exist.** One of
the source catalogs used *category* labels (`device_controls`, `timer_control`, `cooking_control`)
in the same field another catalog used for tool names, and the loader had treated the field as
authoritative. So `cooking_control` was compared against a correctly-dispatched real tool and scored
FAIL.

Corrected: **184 of 246 — 75%**, and the 62 real failures decomposed into something actionable:

```
31  expected NO action, one was taken   <- the dangerous class
26  expected an action, none was taken
 5  wrong action
```

Three more of the same shape were caught in the same session: 25 cases expecting a capability the
observer structurally could not see (they now *skip*, and are counted); a name-form mismatch where
one side wrote `self.get_device_status` and the other emitted `self_get_device_status`; and a
grouping bug that erased the subset label from all 541 negative cases, so the most important subset
reported **0 instead of 72**.

## The rule

**Before a suite's first result is believed, validate the expectations against the system's declared
capabilities.** An expectation referencing something that does not exist is an *unwritten* test, not
a failing one, and it must be excluded from the denominator rather than reported as red.

Then decompose failures by *mode* before triaging by count. "132 failures" is not a finding.
"31 cases where the system acted when it should have refused" is.

## Why it generalises

Every suite has a boundary between what it asserts and what the system can express: API contracts,
schemas, feature flags, tool manifests, permission sets. Whenever expectations are authored
separately from that boundary — by different people, from different sources, at different times —
they drift, and the drift shows up as failures that look exactly like defects.

The cost asymmetry is what makes this worth a rule. A false failure is more expensive than a missed
one: it sends someone to fix working code, and after enough of them the suite gets ignored entirely,
which destroys the instrument. **A red result that is wrong is worse than no result**, because a
missing result is visibly missing and a wrong one is not.

The cheap version of this check is one set-membership test per expectation, run at load time, and it
turns "the suite is red, someone look at it" into "the suite covers 246 of 316 cases and here is what
the other 70 need." Both are honest; only one is actionable.
