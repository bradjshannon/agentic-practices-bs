# `verify_flash` proves consistency, never currency — and the stale file makes it a contaminated control

**2026-08-01, iotta.** Five hours went into a C++ "impossibility" that never existed. The board had
been running a 14.5-hour-old image the whole time, and the check everyone trusted was structurally
incapable of noticing.

## The symptom

A bare admin `/say` produced audible audio, but the device's session state machine never left
`kIdle` — the OLED read "idle" throughout playback, observed independently by a human at the bench.
A fix for exactly that had been written, tested (host suite green) and flashed.

Worse, the evidence looked self-contradictory. An unconditional diagnostic placed as the **first
statement** of the `kTts` case never fired, while a branch a few lines *later in the same case*
logged reliably every time. Two agents reported that as a structural impossibility and asked for
JTAG.

## The cause

The flashed image predated both the fix and the diagnostic. At the SDK commit actually on the
device, `kIdle` handled only `kListenStart`, so `kTtsStart` was a no-op: `after == before`, the
state-change callback never fired, the log never printed. The later branch was state-independent and
always fired. **There was no contradiction — the diagnostic was never on the board.**

## Why the check passed

`esptool verify_flash` compares the device against a **local file**. The local file was the same
stale image. Both sides of the comparison were wrong in the same way, so it matched — a control
contaminated identically to the treatment, which shows agreement and means nothing.

The word to notice is *verify*. It answers **"does this device match this file?"** — consistency.
Nobody asked it the question they thought they were asking: **"is this device running current
code?"** — currency. It cannot answer that, at any level of care.

## What did answer it, and had all along

The device self-reports its build provenance, and the server stores it:

```
app_version   20260801-0233-e89b0c5-d124720
compile_time  Aug  1 2026 02:35:30
sdk_src       path bddeb6d-dirty
```

`git merge-base --is-ancestor <fix> bddeb6d` → **NO**. One command. The fields had been sitting in
the device record for fourteen hours.

## The rules

1. **After a flash, read the artifact's own reported provenance back off the device and compare it
   to the source you meant to ship.** `sdk_src` vs `git rev-parse --short HEAD`. Make it part of the
   flash tooling, not a discipline — this is Structural class and works on an agent that never read
   this file.
2. **When a check compares your artifact to another artifact you produced, ask what would make BOTH
   wrong.** Comparisons against a sibling copy are contaminated controls by default; only a
   comparison against an independent source establishes currency.
3. **An "impossible" observation is nearly always a stale premise about what is running**, not a
   language-level impossibility. Before reaching for a debugger, establish what code is actually
   executing.

Related: `contaminated-control-pytest-collision`, `measure-the-instrument-before-the-effect`,
`live-tree-override-shipped-a-change-nobody-could-see-2026-07-28`.
