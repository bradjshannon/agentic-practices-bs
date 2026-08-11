# Escalating within a hypothesis is not testing it

**2026-08-02.** Two diagnoses failed in a row on "a verified flash won't stick." The answer
was sitting in a log neither of them opened, and had been for an hour.

## The symptom

NIMBE was flashed with a new build. The flash succeeded and hash-verified. Within ~46 s the device
reported the *old* build's `app_sha256` again. Four escalating attempts followed:

1. `idf.py app-flash`
2. register + release the build server-side, then `app-flash` again
3. full `idf.py flash` (all partitions)
4. raw 5-partition `esptool write_flash` including `ota_data_initial.bin`, verified all-`0xFF`

Every one succeeded and verified. Every one produced the identical symptom. By attempt 4 the working
theory had become quite sophisticated — a bootloader OTA-slot-selection defect, possibly a factory
partition fallback, possibly secure boot.

## The cause

None of it was on the device. The server's `/provision` log showed the new build **booting and
running three separate times**, each time answered with an OTA offer of the *old* release, which the
device dutifully installed and rebooted into. The flash had worked on the very first attempt.

## Why four attempts found nothing

Look at what varied. Attempts 1→4 vary the *thoroughness of the write*: one partition, then the
release pointer, then all partitions, then the OTA selector data too. They do not vary the
**hypothesis**, which was fixed at attempt 1: *the new image is not reaching or not being selected
on the device.*

Four increasingly-thorough writes are four repetitions of one assumption, not four experiments.
**No possible outcome of any of them could have produced a different diagnosis** — a failure meant
"still not sticking, go deeper," and even a success would only have said "the deepest write worked,"
never "the write was never the problem." That is the definition of an untestable sequence, and it
feels exactly like methodical progress from the inside. Each attempt is more rigorous than the last,
which is what makes the pattern so convincing and so hard to exit.

The localisation is the trap. Once "the problem is on the device" was adopted, the *server* stopped
being a place anyone would look — not because it was ruled out, but because it was no longer part of
the story. The falsifying evidence was never hidden. It was one `docker logs … | grep <device-id>`
away, in a subsystem the hypothesis had quietly excluded from the search.

## The rules

1. **Before the next attempt, ask what result would make you abandon the theory rather than deepen
   it.** If the honest answer is "nothing this attempt can return," you are not running an
   experiment and should stop and go find an instrument that can disagree with you.
2. **When attempt N+1 is attempt N but more thorough, that is the signal to change subsystems, not
   to escalate.** Thoroughness along one axis is not coverage.
3. **Name the subsystems the hypothesis excluded, and query one of them before escalating.** A
   localisation is a claim, and the cheapest check on it is usually a log in the subsystem you
   stopped considering.
4. **In a client/server loop, always read BOTH ends before diagnosing either.** The device says what
   it is running; the server says what it told the device to run. Neither alone distinguishes "the
   image never landed" from "the image landed and was replaced."

Related: `verify-flash-proves-consistency-never-currency-2026-08-01`,
`ota-release-key-must-match-reported-version`, `measure-the-instrument-before-the-effect`,
`a-symptom-that-resolves-does-not-confirm-the-hypothesis-2026-08-02`.
