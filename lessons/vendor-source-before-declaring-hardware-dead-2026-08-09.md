# Check the vendor's own working example before declaring a peripheral dead

**2026-08-09.** A dev board's SD card had been diagnosed as a hardware fault, escalated to the human
for bench work (second card, DMM the socket pins, continuity checks), and had sat that way for days.
The actual cause was **two GPIO numbers swapped in our board-support header**, and the vendor's own
working demo for that exact board had been public on GitHub the whole time.

## What happened

The symptom was recorded carefully and correctly: `sdmmc_init_ocr: send_op_cond` returning `0x107`
(timeout) on **9 of 9 probes, zero variance**. A prior investigation had noted — rightly — that
*"zero variance is the opposite signature of a flaky or marginal connection"*, and concluded the
failure was code-level rather than mechanical. That conclusion was correct. Nobody then went and
found the reference implementation.

The vendor's demo said `CMD = 38, D0 = 40`. Our header said `CMD = 40, D0 = 38`. With the command
line wired to the data pad, the card cannot answer, ever, identically every time.

## The generalisable rules

**1. "It's code-level, not hardware" is a conclusion that has a next step, and the next step is the
reference implementation.** The investigation stopped one move short. Zero-variance failure had
already ruled out the mechanical explanations; the remaining space was *configuration*, and the
cheapest possible probe on a configuration question is a known-good configuration for the same part.

**2. Search for the vendor's org, not for your symptom.** Symptom searches returned generic
tutorials. Listing the manufacturer's GitHub org and then listing repository *trees* found it in two
commands. First-party or near-first-party sources existed for **every** board on this bench once
someone looked — the manufacturer's own repo for one, several independent community ports for
another.

**3. A repository search that returns nothing needs a positive control before you believe it.**
`gh search code --owner <org> "SDMMC"` returned empty. So did `gh search code --owner <org> "I2S"`,
and so did `"void setup"` — the instrument was blind, not the answer negative. Listing trees via
`gh api repos/<org>/<repo>/git/trees/HEAD?recursive=1` worked immediately. **One empty result from
an uncalibrated instrument nearly closed the search branch.**

**4. Diff the WHOLE pin map, not just the pin you suspect — the result calibrates your confidence
either way.** Here every other pin matched exactly (I2C, all four I2S lines, the LCD backlight), so
the fault was a single transcription slip and the fix was confident. Had several disagreed, the
right response would have been the opposite: suspect the reference, or suspect a board revision
mismatch, and stop.

**5. The vendor source is not an oracle either.** The same demo file defined a pin as GPIO 53 on a
part whose highest GPIO is 48. Treat it as strong evidence, confirm against the schematic where the
stakes justify it, and **report a disagreement rather than quietly picking a side.**

## The cost of not doing this

Bench steps were queued for a human that would have measured continuity against the *wrong* expected
mapping — derived from our own header — and "confirmed" it. A wrong source of truth is worse than
none, because it is believed by default, including by whoever correctly goes to it first.

Downstream, a whole design direction was blocked on the false premise: buffering diagnostic capture
to the on-board SD card, which removes a real-time throughput requirement by construction, was ruled
out for weeks because "that board's SD does not work."

## The one-line version

**Before you attribute a peripheral failure to hardware, spend two minutes finding out whether the
people who made the board published code that drives it.**
