# An uncontrolled before/after inverted the sign of the effect

**2026-08-01.** Not "the number was a bit off" — the measurement said a feature *freed*
memory when it *costs* memory.

## The claim

2026-07-28, two readings of free internal DRAM on an ESP32-S3: **14,867 bytes with the wakeword
off, 38,863 with it on.** Conclusion drawn: enabling WakeNet frees ~22,640 bytes.

That is a strange result, and it was noticed as strange. A hypothesis was raised and honestly
refuted; a discriminating test was run (the gap survived a DMA-free capability mask, killing the
"descriptor-pool artifact" explanation); the verdict was recorded as *"real but not isolated."*

Everyone did the local reasoning well. The claim still survived four days and shaped how people
budgeted memory on the constrained boards.

## What was actually wrong

The two readings differed in **three** variables: wake-state, uptime, and session activity. Only
one was the subject.

Uptime dominates on this hardware. A board that has been up for hours serving sessions has
fragmented and consumed its internal heap, so *whichever arm you happen to sample late looks
starved* — regardless of the setting under test.

Re-run with uptime pinned at ~325 s in both arms and both arms idle:

| | `internal.free` | `internal.min_free` |
|---|---|---|
| wake ON | 26,679 | 9,987 |
| wake OFF | 43,571 | 25,743 |
| **delta** | **−16,892** | **−15,756** |

Wakeword costs ~16.9 KB. The original comparison had the sign backwards.

## Why "it was noticed as strange" did not save it

This is the part worth keeping. The anomaly *was* flagged, investigated, and left open with an
honest verdict. What never happened was re-taking the measurement under control — the effort went
into **explaining** the number rather than **re-measuring** it.

An unexplained result attracts hypotheses. It should first attract a controlled re-run, because
every hypothesis you generate is conditioned on the number being real.

## The rules

- **Two readings taken at different uptimes are not a comparison.** Neither are two readings taken
  under different load. Name every variable that differs between your arms before you subtract.
- **A surprising result is a reason to re-measure, not (only) a reason to theorise.** If a
  controlled re-run is cheap — this one was ~15 minutes of reboots — do it before you build an
  explanation, and certainly before anyone budgets against the number.
- **Require two metrics to agree in sign.** `free` and `min_free` both moved the same way, which is
  what promoted this from "a number" to "a result". Disagreeing metrics mean stop.
- **Automate the control, not the measurement.** The measurement was always easy. What was missing
  was holding uptime and activity constant, and that is what got built into a reusable harness so
  the next question inherits the control instead of the trap.

Related: [[measure-the-instrument-before-the-effect]],
[[a-red-signal-deserves-the-same-suspicion-as-a-green-one]], [[verification-and-evidence]].
