# Attaching the instrument reset the thing being measured

**2026-08-15.** A lot was sent to watch a listen window on an ESP32-S3 board — specifically whether
a voice-activity detector would close it on its own, which was the whole open question. It opened a
serial capture to watch.

**Opening the capture reset the board.** Native-USB ESP32-S3 asserts reset on a DTR toggle, and a
default `pyserial` open toggles DTR. The device reported `reset_reason: 11` (`ESP_RST_USB`). The
window under observation was gone before the first line was read.

## Why this is worse than a silent instrument

A dead instrument gives you nothing, and nothing is at least honest. This one gives you a **live,
correctly-formatted stream of a machine that just rebooted because you started watching**. Every
signal reads healthy. Any conclusion drawn about the pre-attach state is a confident statement about
a machine that no longer exists.

It also destroys the *rare* state preferentially. Steady-state behaviour survives a reboot and can be
re-observed. The transient you attached to catch — a window that only opens occasionally, a wedge, a
leak at hour three — does not. So the failure lands hardest exactly where the observation was most
expensive to arrange.

## The rule

**Before attaching an instrument, ask what attaching it does to the subject** — and treat the first
reading after attachment as suspect until you have confirmed the subject did not restart, reset, or
re-initialise when you connected.

Concretely, for a serial capture on native-USB parts: **pin DTR/RTS before opening the port.** More
generally, look for the equivalent in whatever you are attaching — a debugger that halts on connect,
a profiler that forces a GC, a log level raised at runtime that flushes a buffer, a health endpoint
whose first call warms a cache and changes the number you came to read.

## Why it generalises

Every instrument sits somewhere on a spectrum from passive to invasive, and **nothing about the
reading tells you where.** The output format is identical either way. The only way to know is to
have asked in advance, or to notice a `reset_reason`-shaped field afterwards and check it — which
requires already suspecting the problem.

This is the observer-effect form of a broader failure: *an instrument's own behaviour is part of the
measurement, and it is the part nobody writes down.* Related and worth reading together: a null from
an instrument that never attached looks exactly like a null from a thing that never happened, so a
capture that resets its subject can produce both errors at once — a wrong reading AND a wrong
absence.

## The cheap discipline

When an observation is expensive to arrange (a bench, a rare transient, a human standing by), spend
one command first on **proving the instrument is attached and the subject is undisturbed** before
spending the opportunity. A boot counter, an uptime field, a session id — anything that would change
if attaching had perturbed the subject. If that check is not available, say so in the report, because
then the reading carries an unquantified risk rather than none.
