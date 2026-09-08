# A decoded coredump is evidence of a past crash, not proof it's the CURRENT symptom's cause

**Symptom.** A board ("DURIN") wouldn't boot past a single static LED state — power-cycle
confirmed (amp click), but it never reached the next boot stage. Pulled the on-flash coredump
partition, found the matching archived ELF via the device's own firmware store (keyed by the
coredump's embedded SHA256), and decoded a real, well-formed crash: `abort()` from
`ESP_ERROR_CHECK(esp_wifi_init(&init))` returning `ESP_ERR_INVALID_ARG`, with a full symbolized
backtrace pointing at one exact line. This read as a confirmed, reproducible firmware regression —
confident enough to report as "root cause found" and dispatch a fix lot against it.

**What actually happened.** The fix lot's own investigation — asked to root-cause AND verify on
hardware, not just accept the diagnosis — could not reproduce the WiFi-init failure in a clean
rebuild (traced every dependency the coredump's build carried, found nothing misconfigured). It
then discovered the board's chip was permanently re-entering the ROM's serial download bootloader
on every reset, **regardless of what was flashed** — ruled out via a positive control (an
identical-model board captured normal boot output immediately with the same tooling) and by ruling
out flash corruption and secure-boot/efuse lockout. That signature — enumerates fine, but no app
ever runs — is consistent with the BOOT/GPIO0 strapping pin being held low externally (a stuck
button, something resting on the board), sampled fresh at every reset before any app code, firmware
included, gets a chance to run. The operator pressed the physical BOOT button several times; the
board booted clean immediately after, past the exact WiFi-init call the coredump had implicated.

**The coredump was real** — it genuinely captured a real past abort, correctly decoded, correctly
attributed to a real line of code. It was simply evidence of a **different, earlier** problem than
the one currently being observed. Two independent faults landed on the same board in the same
session, and the fully-decoded one was mistaken for an explanation of the live one because it was
the only lead with a symbolized backtrace attached — which reads as far more authoritative than a
build-vs-serial-port anomaly with no stack trace at all.

**The rule.** A coredump (or any crash artifact with a clean backtrace) answers "what did the code
do the last time it aborted", not "why is the device behaving this way right now." Before treating
a decoded crash as the explanation for a currently-observed symptom, check that the crash's
timestamp/build actually corresponds to the CURRENT failure, not an earlier one sitting in
persistent storage from a previous flash or run — a coredump partition survives across reflashes
and reboots by design, so its presence proves nothing about recency. Where the two diverge (as
here: the archived ELF traced back to a different worktree's build than what the device now
reports), that divergence is itself the tell that the artifact may be describing history, not the
present.

**Why it generalises.** This is the general shape of "the salient measurement crowds out the
falsifying one" — a fully-explained, symbolized, single-cause story is psychologically stickier
than an ambiguous multi-symptom one, even when the ambiguous one (device enumerates but nothing
runs, unaffected by flash content) is actually the sharper discriminator between "firmware bug" and
"physical/electrical fault." The corrective mechanism that caught it here wasn't better initial
analysis — it was briefing the fix lot to **verify on real hardware** rather than accept the
diagnosis and build a patch for it. A subagent tasked with "confirm and fix" is a genuine check on
the dispatcher's own confident wrong turn, not a redundant formality; do not skip the reproduction
step because the analysis already looks airtight.
