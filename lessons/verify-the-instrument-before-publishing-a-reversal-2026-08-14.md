# Verify the instrument before publishing a reversal (2026-08-14)

## Symptom

An agent reversed a documented hardware fact, published a confident mechanism explaining it,
then reversed back — twice in ten minutes — and propagated both wrong versions into a live
subagent's brief.

## What actually happened

A battery-percentage display read 0% on a healthy cell. The chain under it:

1. Operator measured pack voltage (3.970 V) and the agent read the firmware's sense-pin
   telemetry (2299 mV). Implied divider ratio 1.727 against a firmware constant of 1.33.
   **Conclusion published: the constant is wrong.**
2. The agent then consulted the authority it should have consulted first — a maintained
   hardware-reference page — which gave the divider from the vendor schematic as
   `(33k + 100k) / 100k = 1.33`, operator-confirmed. **Conclusion reversed: the constant is
   right, so the ADC must be under-reading.**
3. A direct probe of the divider node returned 3.20 V, which is *above* the ADC's usable range
   at its configured attenuation. **A complete, vivid mechanism assembled itself**: the node
   clips at normal charge, so the reading is meaningless across the whole useful battery range,
   and no software fix is possible because the divider is mis-scaled for the ADC.
4. The operator asked, unprompted, *"let me confirm where io5 lands on the castellation"* —
   and re-probed. The correct pin read **2.333 V**, 1.5% from what telemetry reported. The ADC
   was accurate the whole time and nowhere near its ceiling. **The 3.20 V had been taken from
   the wrong side of the module.** Step 1's conclusion was right all along.

Every downstream conclusion in step 3 was sound reasoning over one bad number.

## The rule

**Before publishing a reversal of a documented claim, ask what would make the new reading
itself wrong.** For a hardware measurement that is almost always the probe point; for a query
it is the scope or the filter; for a log it is whether the instrument was running.

The tell is *how well the new story explains things*. A reversal that arrives with a complete
mechanism attached feels like a discovery and reads as one. A weaker story invites a second
look; a strong one closes the question before it has been asked.

## Why it generalises

This is not about hardware. It is the shape of every confident wrong conclusion built on a
single un-cross-checked input: a `grep` scoped to one directory that "proves" a file is
missing, a query against the wrong environment, a null from an instrument nobody confirmed was
running. The reasoning downstream is usually impeccable, which is exactly why the reasoning is
not where the error can be caught.

Two supporting notes from the same run:

- **The authority existed and was consulted second, not first.** Step 2's page had the
  schematic values *and* the ADC caveat. Reaching for it before publishing step 1 would have
  produced the same eventual answer with one reversal instead of two.
- **A reversal is cheap to hold and expensive to broadcast.** Both wrong versions went into a
  running subagent's brief and had to be retracted mid-flight. A conclusion that is one
  measurement from being settled can wait for that measurement.

## Related

`measure-the-instrument-before-the-effect.md` — the same principle applied before an
experiment rather than after a surprise. This lesson is its failure-mode counterpart: the
instrument gets checked when the *result* is surprising, and a result that arrives with a
satisfying explanation does not feel surprising.
