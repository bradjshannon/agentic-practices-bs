# An OTA release key that isn't the version the image reports is an infinite reboot loop

**Symptom.** A board takes an OTA, comes up, provisions — and then reboots every ~90 seconds
forever. From the bench it looks like a permanent "CONNECTING". Health telemetry freezes at the
pre-reboot snapshot, `crash_count` stays 0, and no crash or coredump is produced. It reads
exactly like a firmware defect in whatever feature you just shipped.

**What actually happened.** The firmware image embeds its own version string (here
`20260730-1539-36c2573`, derived from the commit). The image was *registered and released* under
a different, human-chosen key (`taptest-36c2573`) to dodge a 31-character limit on the release
name. The server decides whether to offer an update by comparing the version the device reports
against the released key. Those two strings can never match, so:

1. device boots, provisions, reports `20260730-1539-36c2573`
2. server sees released `taptest-36c2573` ≠ reported → offers the update
3. firmware's `on_update_ready` callback calls `esp_restart()` immediately
4. go to 1

The device was healthy the entire time. Nothing was wrong with the feature that had just been
flashed.

**The cost of not knowing this.** It happened twice in one afternoon. The first time it was
diagnosed as internal-DRAM starvation — on the strength of a *real* measurement (`idram_min: 75`
bytes of headroom on the working build) that had nothing to do with the failure. A fix was
designed, built, tested and shipped for the wrong cause. The correlation was genuine; the causal
story was invented around it.

**The rule.**

- **Register and release an image under the exact version string the image itself reports.**
  If you must name it, read the name out of the built binary rather than choosing one.
- If a release-naming limit forces a shorter name, that is a signal to fix the *firmware's*
  version scheme, not to invent a release alias.
- **Before diagnosing a post-OTA loop as a defect in the shipped feature, compare the device's
  reported version against the release pointer.** One command, and it rules out the entire class.
- **Count boots before calling something a hang.** A device event log with `boot` records ~90 s
  apart is a loop; a single boot with long silence is a hang. They have different causes and the
  bench symptom is identical.

**Why it generalises.** Any update system that decides "is this device current?" by comparing an
identifier the *device* produces against one a *human* typed has this failure mode. The two
identifiers come from different sources and nothing enforces that they agree, so a mismatch is
silent, self-perpetuating, and indistinguishable from a crash in the new payload. The general
form: **when a control loop compares two strings from different authorities, a naming mismatch
does not read as a naming problem — it reads as a fault in whatever the loop was controlling.**
