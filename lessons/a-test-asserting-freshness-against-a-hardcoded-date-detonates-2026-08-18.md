# A test that asserts freshness against a hardcoded date detonates on a date nobody chose

**2026-08-18, iotta.** A green suite went red with no commit behind it.

## What happened

`test_matrix_reflects_recorded_calibrations` posted a calibration record with
`last_run_at: "2026-07-19T00:00:00+00:00"` and asserted the resulting status was `"done"`.

The staleness window is 30 days. On 2026-08-18 the fixture crossed it, the status became `"stale"`,
and the test began failing permanently. Nothing was committed that day. The test passed when it was
written and could never pass again.

## The two ingredients, and neither alone is enough

1. **A hardcoded timestamp in the fixture.** Common, usually harmless.
2. **A code path that resolves NOW internally** rather than accepting it as a parameter.

The same codebase had the safe version right next door: `status_for(last_run_at, *,
stale_after_days, now)` takes `now` explicitly and is deterministic forever. The HTTP handler one
layer up resolves `now` at call time — and that is the layer the failing test exercised. So "does
this module take a clock?" is the discriminator, not "does this test hardcode a date."

## Why it is worse than an ordinary red test

It arrives **attributed to whoever is standing nearest**. A suite that was green yesterday is red
today, so the natural reading is that the change in flight broke it. Here a subagent's branch was
under review at that exact moment; without a control the failure would have been charged to that
branch, and the branch would have been "fixed" until the symptom moved.

**The control is one command and it is the whole lesson:** run the failing test on a clean checkout
of the base commit, *before* attributing it to any branch. Identical failure = pre-existing.

## Fixing it without gutting it

Anchoring the fixture to `now - 1 day` makes it pass. It also makes it possible to "fix" the test
into something that can no longer fail. Run both directions:

- fixture at `now - 1 day` → **passes**
- fixture at `now - 40 days` → **still fails**

If the second one passes too, the assertion has been neutered rather than repaired.

## What does NOT generalise, measured

Grepping the suite for hardcoded ISO timestamps returned **82 files** — far too broad to act on,
because most are inert fixture data never compared against a real clock. Narrowing to files that
also mention a freshness verdict (`"stale"` / `"expired"` / `stale_after`) gave **10**. Even that is
a candidate list, not a finding: none of the other nine had detonated.

The honest cheap detector is a single **clock-shifted suite run** — shift NOW forward, see what
flips. One run answers it for every test at once, where a file-by-file audit answers it for none.
It was considered and NOT built here: patching a global clock breaks unrelated timestamp
comparisons, and a check with a high false-positive rate gets bypassed and takes its true positives
with it.

## The generalisation

Any assertion whose truth depends on the gap between a **stored constant** and **wall-clock now**
has an expiry date. Freshness and staleness are the obvious cases; so are certificate validity,
token expiry, retention windows, "recent" filters, and cache TTLs. The bug is not the constant —
it is that the constant and the clock move relative to each other, and only one of them is in the
repo.
