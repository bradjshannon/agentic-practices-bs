# A staleness check keyed on a string the fix does not remove can never fail

**2026-08-01, iotta.** A status card claimed a device tool ignored its arguments and rebooted
unconditionally. It carried an automated freshness check, and that check said **HOLDS** on the
morning sweep. The premise had been dead for a day.

## What happened

The card's claim: `reprovision`'s handler takes an unused `std::string_view`, so the server's
`defer_until_idle` preference is discarded and a device mid-conversation gets rebooted.

The attached check:

```
file-contains  main/app_main.cpp  "session token cleared, rebooting"
```

The fix that landed the day before (`cd26752`, an ancestor of `HEAD`) added a whole deferral
component: the handler now parses `defer_until_idle`, arms a poll loop, folds the deferral into
telemetry, and has timeout and reached-idle log lines. **It also, correctly, kept the original
immediate-reboot branch** — that is the `defer_until_idle=false` path, and removing it would have
been the bug.

So the string the check looked for was still there. It will always be there. The check was
incapable of failing, and it spent a day telling the sweep the card was fresh.

## The general shape

A staleness check is a **falsifier**. Authoring one is designing a test, and it inherits the same
failure: a test with no path to failure passes forever and reads as evidence.

The specific trap is that the natural thing to key on — a string from the *broken* behaviour — is
very often a string the *fixed* code still contains, because a good fix usually adds a branch
rather than deleting the old one. The check then asserts "this code still has a
reboot-immediately path", which is true of the broken version **and** of the fixed version.

## The rule

**Key a check on something the fix must DESTROY or must CREATE, never on something it may keep.**

- Bad: the premise's symptom string (`"...rebooting"`). Survives the fix.
- Good: the *absence* of the thing the fix adds (`file-contains "defer_until_idle"` expected NOT
  to hold), or a commit/merge assertion (`git log -S`, `merge-base --is-ancestor`).

Before attaching a check, answer one question in writing: **what change to the world makes this
check flip?** If the honest answer is "a rewrite nobody plans to do", the check is decoration and
the card is better off with no check at all — an absent check reads as unknown, which is true,
while a check that cannot fail manufactures confidence.

## The compounding error, which is the reason this is worth a file

Having read `HOLDS` on the sweep, the conductor then briefed a subagent to **build the fix that
already existed** — without running `git log -S` on the file first, which its own contract puts
*before* writing a brief rather than after the agent reports. A green instrument is not a
substitute for the one command; it is exactly what makes you skip it.

Related: `verification-and-evidence.md`, `a-warning-you-can-ignore-is-not-a-control.md`,
`when-a-figure-stops-reproducing-someone-may-have-fixed-it.md`.
