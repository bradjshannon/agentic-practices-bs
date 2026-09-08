# "connected: true" in a device registry is API liveness, not physical USB presence — check both axes separately

## Symptom

An oracle work-assignment pass, relying on `GET /devices` API state, listed a board (P4) as one of
several "confirmed live" boards and briefed hardware work against it. The board had not been
physically connected to the machine that session at all. A later pass explicitly checked physical
USB enumeration (`Win32_PnPEntity`, filtered on the vendor VID) alongside the network state and
found the opposite failure mode too, on a *different* board: AMOLED was physically present (a real
COM port enumerated) but had been API-dead for 93 hours.

## What actually happened

"Connected" in a device-registry read is a statement about the last time the *server* heard from
the device over its existing session — it says nothing about whether the device is currently
plugged into *this* machine's USB bus. A board can be network-live via a completely different host
(or simply still mid-session from hours ago with no fresh heartbeat expected soon), while being
physically absent from the bench being worked at. The reverse is equally real: a board can sit on
the desk, enumerated and ready to flash, while its own connection to the server has been down for
days for an unrelated reason.

## The rule

**Before briefing or dispatching hardware work against a specific board, check physical presence
and network liveness as two separate, independently-verified facts** — not one as a proxy for the
other. Physical: enumerate the actual USB devices on the machine that will do the work (vendor
VID filter, or a roster-matched COM port scan). Network: the registry's own `connected`/
`last_seen` state. A board is fundable for on-bench work only when both are current; a board that's
API-live but not physically present needs someone to go find and plug it in first, not a flash
attempt that will simply fail to locate a port.

## Why it generalises

Any fleet/device-registry-backed system that reports "connected" is reporting session state, not
presence — this is not specific to this project's protocol. Any agent about to spend real hardware
lot budget on a board should verify presence at the physical layer it will actually operate at
(the machine doing the flashing/serial work), not the network layer the registry reports.
