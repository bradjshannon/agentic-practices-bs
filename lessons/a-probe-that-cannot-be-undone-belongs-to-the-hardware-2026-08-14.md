# A probe that cannot be undone belongs to the hardware, not to the software

**Symptom.** A read-only-looking diagnostic sequence — call a tool, observe the reply — took a
board off the network for sixteen minutes and left an amplifier driving DC into a speaker coil at
60-65 °C. Every individual call was a documented device tool with a bounded server-side timeout.

**What actually happened.** The tool wrote audio to an I²S channel in a per-chunk loop.
`i2s_channel_write()` was called with a bounded per-call timeout, but its return code and byte
count were **never checked** — the loop advanced its cursor unconditionally, so a stalled DMA queue
was invisible and it marched on chunk count alone. It therefore never reached the channel-disable
call on that path. The board's amplifier had **no enable pin**, so the only thing that ever
silences it is what the I²S pins carry: bit clock still running, data line frozen on a non-zero
sample, DC into the coil until a human unplugged the speaker.

**The rule.** Before running a diagnostic that actuates a physical output — a speaker, a motor, a
heater, a radio — ask what the hardware does if the call never returns, and check whether software
has any way to stop it. Where the answer is "nothing, there is no enable line", the probe is not
reversible and its cost is not bounded by a timeout. Run it once, watch the physical thing, and
treat a call that has not returned as an emergency rather than as a slow call.

**Why it generalises.** The instinct that a read-only-looking API call is a safe probe comes from
software, where the worst case of a hung call is a hung call. An actuator inverts that: the *stall*
is what causes the damage, because a stalled writer leaves the last commanded value asserted
forever. The generalisation is that **"bounded timeout" bounds the caller, not the effect** — any
output that latches its last value turns a software stall into a continuous physical action, and
the absence of a disable path turns that into an unbounded one.

Two corollaries worth carrying:

- **Audit the enable path per board, not per driver.** In the estate this came from, two of four
  boards could mute their amplifier from firmware and two could not — same driver, same tool, and
  the hazard existed only on the two with the pin missing. A capability flag said "this board has
  an amplifier" on all four, which is a different question from "this board can turn it off".
- **A stall that outlives its own timeout is unexplained, not merely slow.** Here the software
  stall analysed to tens of seconds and the observed outage was sixteen minutes. Fixing the
  software gap was correct and did not close the gap in the explanation; saying so is what stops
  the residual from being quietly assumed away.
