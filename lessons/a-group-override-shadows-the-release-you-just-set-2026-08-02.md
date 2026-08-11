# A group override shadows the release you just set — and `firmware-list` still says "(released)"

**2026-08-02.** Sibling of `ota-release-key-must-match-reported-version`: same control loop,
same silent self-perpetuating revert, different mismatch. There the two strings came from different
*authorities*. Here they come from different *pointers*, and the operator only knew about one.

## The trap

The server's OTA releases are **layered**: a per-board default, plus optional per-group overrides
(`firmware-release <board> <version> --group <name>`). `resolve_meta` prefers the group override when
the device's group has one. This is documented in `docs/devices.md` and is a deliberate
targeted-rollout feature — the bug is not in the layering.

The trap is that **the shadowed case is invisible at the point of use**. Running

```
myproject-devices firmware-release esp32-s3-rgb-matrix 20260801-2325-d767c86
```

sets the board default, prints success, and has **no effect whatsoever** on a device whose group
carries an override. `firmware-list` then shows the new build tagged `(released)` — which reads
exactly like "this is what devices will be offered." It isn't. The stale group override is what the
loop actually reads, and it is on a different line.

Consequence: the device provisions, is offered the *old* build, installs it, reboots, and reports the
old version. It looks identical to a flash that will not stick, and it survives arbitrarily thorough
reflashing, because every reflash is undone within ~46 s by an OTA nobody realises is happening. Four
escalating flash attempts and two failed diagnoses went into this before anyone read the server's
`/provision` log.

## The fix that worked

```
myproject-devices firmware-release esp32-s3-rgb-matrix 20260801-2325-d767c86 --group default
→ 20260801-2325-d767c86  2133648 bytes  sha256=55024d53ed08…  (released, group:default)
```

Both pointers now agree, so the next provision has nothing older to offer.

## The rules

1. **After any `firmware-release`, resolve what the *device* will actually be offered — do not trust
   the release command's own success line.** The authoritative check is the device's group plus the
   override table, or simply the next `/provision` log line.
2. **`(released)` in `firmware-list` answers "is this the board default," not "is this what devices
   get."** Read the group column on the same row before concluding anything.
3. **When a board reverts after a flash, read the server's `/provision` decisions before touching the
   device again.** It records both the version the device reported and the version the server
   offered; that pair distinguishes "the image never landed" from "the image landed and was replaced"
   in one line. Nothing on the device can make that distinction.

## The structural fix

The operator-facing surface should make the shadowed case unrepresentable rather than merely
documented. Two candidates, in order of preference:

- **`firmware-release` without `--group` should warn (or refuse) when a group override exists for
  that board**, naming the groups that will not be affected. The information is fully available at
  the moment the misleading success line is printed.
- **`firmware-list` should mark a board-default row as `shadowed for: <groups>`** so `(released)`
  cannot be read as "effective."

Generalises to any layered-config system: **when a higher-priority layer can silently shadow the one
you just wrote, the write path must say so at write time.** Documenting the precedence elsewhere does
not help, because the person about to be bitten has already decided which command to run.

Related: `ota-release-key-must-match-reported-version`,
`escalating-within-a-hypothesis-is-not-testing-it-2026-08-02`,
`verify-flash-proves-consistency-never-currency-2026-08-01`, `myproject-server/docs/devices.md`.
