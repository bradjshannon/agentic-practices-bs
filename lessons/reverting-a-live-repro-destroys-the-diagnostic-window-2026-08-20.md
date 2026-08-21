# Reverting a live, reproducing hardware failure destroys the diagnostic window it needs

**Symptom:** a device was hanging reproducibly at boot. The coordinator's reflex, on hearing
"it froze twice in a row," was to instruct the diagnosing agent to stop, revert the device to the
last known-stable build, and diagnose offline via static analysis — "get it back to stable first."

**What actually happened:** the operator corrected this directly: the revert instruction "ruined
our best chance of troubleshooting." The one real finding that session (a specific task's watchdog
trip, later root-caused to a busy-spin) came from a serial logger that happened to already be
running when the operator power-cycled the device *before* any revert took effect — not because
of the revert instruction, in spite of the instinct behind it.

**The rule:** when a bug is actively, reproducibly failing AND you have instrumented access to it
(serial, remote logs, a debugger), that combination is rare and time-limited. Recovering the
device/system to a safe state can almost always wait a few more reproductions unless the cost of
*not* recovering is itself unacceptable (data loss, an unrecoverable device, a production outage).
"Get it back to stable" is the right default when you do NOT have the instrumented window; it is
the wrong default the moment you do.

**Why it generalises:** this is not specific to embedded/hardware debugging. The same shape shows
up anywhere a fault is transient and reproducing under observation — a flaky service, a race
condition caught mid-flight, a corrupted-state bug live in a debugger. The instinct to restore
safety first is a genuinely good default in general, which is exactly why it needs an explicit
override: name the two costs (one more reproduction vs. losing the window) before defaulting to
recovery.
