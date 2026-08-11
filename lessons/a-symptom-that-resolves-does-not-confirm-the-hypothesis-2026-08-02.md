# A symptom that resolves does not confirm the hypothesis — check whether the fix falsified it

**2026-08-02, iotta.** I diagnosed a board's failure-to-connect, prescribed an action, the action
worked, and my diagnosis was wrong. The two facts are compatible, and nearly got recorded as
agreement.

## What happened

NIMBE stopped answering `esptool` — "Write timeout" before any bytes were written. I got the ROM
banner off it and read, verbatim:

```
rst:0x15 (USB_UART_CHIP_RESET),boot:0x16 (SPI_DOWNLOAD_BOOT)
wait spi download
```

That observation was correct: the chip was in a download mode `esptool` cannot speak. From it I
inferred a *cause* — that GPIO46 was being held high by something external on the board's expansion
header, or by a pull-down resistor damaged in a recent solder rework. I told the operator to detach whatever
was on that header and power-cycle.

He power-cycled. It came up fine. **And nothing had ever been attached to that header** — which
falsifies the inference outright. The prescribed action worked for a reason unrelated to the reason
I gave.

## Why this is dangerous rather than merely embarrassing

The natural write-up is "diagnosed strap conflict on IO46; resolved by detaching and power-cycling."
Every clause is something that happened. The causal claim in the middle is unsupported, and it would
have entered the record as a *confirmed* board fact — the kind that gets cited months later to tell
someone their own pin numbers are wrong.

Prescribing a broad action ("detach things and power-cycle") is what makes the confusion possible. A
broad action resolves a whole class of causes at once, so its success discriminates between none of
them. The narrower the prescribed action, the more its success actually tells you.

## The distinction to hold

- **The symptom resolved** — an observation about the world.
- **The hypothesis was confirmed** — a claim that requires the fix to have acted *through the
  mechanism you named*.

These come apart whenever the remedy is broader than the theory. Here the remedy included a
power-on reset, which clears state my theory said nothing about; the leading explanation now is a
sticky `FORCE_DOWNLOAD_BOOT` RTC bit, which survives a chip reset (explaining why three of my own
DTR/RTS resets did *not* clear it) but not a true power cycle. That is a *better* candidate — it is
still not confirmed, and I recorded it as an unresolved disjunction rather than promote it into the
gap the old theory vacated.

## The rules

1. **When the fix lands, ask which parts of your hypothesis it actually exercised.** If the remedy
   was broader than the mechanism, you learned that the symptom is gone and nothing more.
2. **A detail of the prescription that turns out to be counterfactual falsifies the hypothesis, even
   though the symptom resolved.** "Detach the thing" succeeding when there was no thing is
   disconfirmation, not support.
3. **Say so explicitly in the handoff, and separate the surviving observation from the dead
   inference.** `boot:0x16 (SPI_DOWNLOAD_BOOT)` is measured and keeps its value; "IO46 was held high
   by an attached satellite" is dead and must not survive as a board fact.
4. **Do not immediately install the next-best theory in the vacancy.** A replacement hypothesis
   inherits the credibility of the slot, not the evidence. Record the disjunction and what would
   separate its branches.

Related: `a-red-signal-deserves-the-same-suspicion-as-a-green-one`,
`instrument-silence-not-data-six-nulls`, `how-to-rank-disagreeing-sources`,
`escalating-within-a-hypothesis-is-not-testing-it-2026-08-02`.
