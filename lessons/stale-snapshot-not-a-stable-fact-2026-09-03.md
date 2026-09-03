# A single live measurement is not a stable fact, even when it's real

**Symptom:** An oracle-dispatched investigation read NIMBE and CLERE's DRAM health live and
reported `idram_big=72` bytes on both boards — a real, correctly-quoted measurement at the moment
it was taken. That figure went into a durable handoff record (`needs-you.md`, `docs/TODO.md`) as
"NIMBE and CLERE are genuinely DRAM-critical." A later, independent re-check minutes later found
NIMBE=416, CLERE=2176 — not converged at all, and CLERE actually ~5x healthier than NIMBE across
its whole recorded history.

**What actually happened:** The fluctuating counter was sampled once and treated as the steady
state. It wasn't lying — it was a genuine reading — but a point reading of a volatile signal was
written into a record as if it were a stable fact about the hardware. The correction required
editing two files in place after they'd already been committed and pushed once.

**The rule:** Before writing a fluctuating hardware/telemetry reading into a durable record (a
handoff doc, a queue card, a decision log), pull the metric's `health_history` (or equivalent) and
cite a range or a "chronic vs. transient" characterization, not a single point value — even when
the point value came from a real, correctly-executed measurement just moments before. "X reads 72
right now" is fine as a thing-to-check-next; "X is critical at 72 bytes" is a claim about the world
that a single sample cannot support for a volatile counter.

**Why it generalises:** This applies to any noisy/bursty signal a conductor or agent might quote as
settled fact — RSSI, queue depth, memory watermarks, latency percentiles, error rates sampled over
a short window. The failure mode is specifically "real data, wrong level of confidence," which is
harder to catch than a fabricated number because nothing about the measurement itself is wrong.
