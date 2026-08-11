# A Windows-side checkout rewrites the bytes your comparison depends on

**2026-08-11. Three instances in one night, in three unrelated subsystems.** Each looked like a
different bug. All three are the same shape: a file's *content or metadata* is rewritten by the
checkout layer, and something downstream compares it byte-exactly against an artifact produced
somewhere else.

## The three

| symptom | what it actually was | how it failed |
|---|---|---|
| A service's own integrity check reported **68 of 74 source files "drifted"** from the commit it claimed to be running | `core.autocrlf=true` on the Windows checkout vs an LF-hashed manifest built in WSL | **Loud and permanently wrong.** Nobody could read it, so nobody read it |
| A three-way hook comparator flagged a file as diverged, 141 lines on both sides | CR-vs-LF only; byte-identical after stripping | **Noise inside a real signal.** It sat among genuine divergences |
| A deploy workflow died in 7 s with `Permission denied`, exit 126 | The execute bit was gone from a script edited through a Windows-mounted path | **Loud and late.** It failed at the moment someone ran it, arbitrarily far from the edit |

The first two are content; the third is metadata. Treat them as one family — the checkout layer
does not promise to hand you the bytes, or the mode bits, that were committed.

## Why it is worth its own lesson

**The failure is not "the files differ."** It is that a *verification mechanism* — the thing whose
job is to tell you when something is wrong — becomes unable to distinguish a benign convention from
a real change. Once it reports drift on everything, a genuine one-line edit is invisible in the
noise, and the check has become strictly worse than no check: it costs attention and returns
nothing.

The 68-of-74 case had been reporting that way indefinitely. Nobody had raised it, because a field
that is always red teaches you to skip it.

## What to do

- **Normalize before hashing, on whatever side you control, unconditionally.** No `sys.platform`
  gate — the verdict must be the same wherever the check runs, or you have moved the problem rather
  than fixed it. Where the other side is an opaque digest you cannot re-derive (a package manifest,
  a signed hash), normalizing your own side is the whole available fix; say so rather than implying
  symmetry you do not have.
- **Then prove it is not a mute button.** After normalizing, make a real one-byte content change
  and confirm the check still fires. A fix that silences everything and a fix that works look
  identical from the pass/fail line. This is the same trap as *a check that cannot fail reports
  HOLDS forever*, arriving from the opposite direction.
- **Annotate line-ending-only differences as such**, rather than suppressing them. A comparator
  that prints `(identical apart from line endings)` stays honest; one that silently drops them
  cannot later tell you the convention itself changed.
- **When a mode bit matters, do not rely on the checkout to carry it.** An execute bit lost this
  way fails loudly but at an unpredictable time. Anything with a meaningful `+x` reached through a
  cross-OS mount is a candidate: deploy scripts, entrypoints, git hooks.

## The generalization

Whenever a comparison spans two environments, ask **what each side promises about the bytes** —
before debugging the difference it reports. If either side is a checkout, a mount, or a sync, the
answer is usually "less than you assumed", and the bug is in the comparison rather than in the
thing being compared.

The diagnostic that settled the first case in minutes, after the symptom had stood for far longer:
the byte-delta equalled the line count exactly on every drifted file, and the handful of clean
files were precisely the pure-LF ones. **A difference that correlates with a structural property of
the file, rather than with its content, is not drift.**
