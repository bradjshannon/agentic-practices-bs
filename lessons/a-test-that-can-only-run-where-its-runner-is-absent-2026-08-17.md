# A test that can only run where its runner is absent never runs (2026-08-17)

## Symptom

A design document named one test as the thing that had to be written before any code: an
assertion that, if it failed, reversed the entire design. The test was written, it was correct,
its suite went green — and it had executed **zero times**.

## What actually happened

The design's central claim was that an audio encoder is fully reset between segments, so encoded
frames are context-free and safe to cache and replay. The claim had only ever been established by
**reading the Python wrapper**; the C binding to the native library underneath was never checked.
The document said so, and asked for a falsifier: encode the same input twice with a reset in
between, assert the outputs are byte-identical.

The falsifier was written as an ordinary pytest file, guarded with `importorskip` on the native
module so it would skip cleanly where the library was absent. That guard is normally correct
practice — a mocked encoder is trivially deterministic and would have made the assertion vacuous,
so refusing to run beats running against a fake.

The problem was the intersection:

- **CI and the dev workstation** have pytest, and do **not** have the native library → skip.
- **The server container** has the native library, and does **not** have pytest → cannot run at all.

There is no environment where both are true. The test could report only "skipped", forever, while
sitting in a green suite next to tests that genuinely ran. Absence of the library and absence of
the test are the same output.

The fix was to make the file executable **without** its runner — pytest imported optionally,
fixtures defined only when it is present, and a `__main__` block that runs the same three
assertions and exits non-zero on failure. Then it was piped into the container over stdin and
actually run. It passed, including a positive control confirming that different input still
produces different output — without which an encoder returning nothing at all would also have
reported "identical".

## The rule

**Before trusting a test that guards a load-bearing assumption, name the environment where it
actually executes.** If you cannot name one, you have written documentation in the shape of a test.

The check is mechanical: list what the test needs (a library, a device, a network, a credential,
a fixture file) and list what each candidate environment provides. A test whose requirements are
satisfied by no row in that table is not "conditionally skipped" — it is dead, and it is dead in
the most expensive way, because it looks alive in a green suite.

## Why it generalises

Skip-guards are added for good reasons and are usually right. The failure is not the guard; it is
never asking whether the guarded-for condition is *ever false anywhere you run tests*. That
question is easy to skip precisely because the guard makes the suite tidy — a skip reads as
"handled", not as "never verified".

The shape recurs well beyond native libraries: integration tests needing credentials no runner
holds, GPU tests in a CPU-only pipeline, tests requiring a service that only exists in an
environment where the harness is not installed. In every case the honest state is `could_not_run`,
and it should be as visible as a failure — but the default reporting collapses it into the same
quiet dot as a pass.

Two things worth doing whichever way it lands:

- **Make the check runnable by the plainest means available** (a `__main__`, a shell script, a
  one-liner), so the environment that has the capability can exercise it without also needing your
  test framework.
- **Record the measured output where the claim lives**, not only in the test. A test that ran once,
  in a place nobody can easily reach, is evidence — but only if someone can find the result without
  reproducing the setup.
