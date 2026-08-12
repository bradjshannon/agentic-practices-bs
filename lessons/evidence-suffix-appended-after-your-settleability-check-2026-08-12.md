# A CLI flag that appends text after your own can silently break a check on what you typed

**Date:** 2026-08-12. **Cost:** ~15 minutes of debugging a "settleability" refusal on a card whose
own visible text plainly satisfied the rule the tool said it failed.

## Symptom

A status-page card-filing tool refuses to write a card flagged `needs: decision` unless it can find
a settleable "ASK: ...?" paragraph in the card's own text — a guard against filing an unanswerable
decision request. A card was constructed with an explicit `ASK: <question>?` sentence as the last
line of its `--detail` argument, and a separate `--evidence` flag supplying the supporting data.

The tool refused it every time, with the exact message the guard prints when NO ask paragraph can
be found at all — even though the ask paragraph was plainly present and ending in a question mark
in the text as typed. Testing the underlying check function directly, in isolation, against the
identical string: it passed. Testing it via `subprocess` with a clean argv (no shell involved):
still failed. The logic was right; something about invoking it live was different.

## What actually happened

The tool has a separate, earlier feature: when `--evidence` is supplied, it appends
`"  EVIDENCE: <text>"` onto the *end* of whatever `--detail` string was given, so evidence always
travels with the claim it supports. The settleability check runs *after* that append, on the final
assembled text — and it isolates the "paragraph" following the `ASK:` marker by splitting on a
double newline (`\n\n`), not by end-of-string.

Because the hand-typed `--detail` had no blank line after its `ASK: ...?` sentence, the append
landed in the *same paragraph* as the ask, by the check's own definition. The paragraph the check
actually evaluated was not `"...real streaming path?"` — it was
`"...real streaming path?  EVIDENCE: grep -c ... = 989..."`, which does not end in `?`, and the
check correctly (by its own rules) called that unsettleable.

Every direct test of the logic passed because every direct test used a short, evidence-free string
that happened not to trigger the append — the bug only exists in the intersection of two features
that were each individually well-behaved and separately tested.

## The rule

**When a tool assembles user input from multiple flags before validating it, validate the
assembled result, not your mental model of what you typed — and know which flags mutate which
other flags' content before you rely on paragraph or position-based text logic.** Concretely here:
give a marker-based text check (ASK block, TODO marker, sentinel comment) its own paragraph with
an explicit trailing blank line, rather than letting it be the last text in a field that another
flag might append to. Don't assume "the last thing I wrote" stays the last thing in the field.

Read the tool's own append logic before debugging the check that consumes it — the check was never
wrong; the assembled input it was checking was not what a human reading the `--detail` string alone
would assume.

## Why it generalises

This is the general shape of **"validation of a derived value, debugged as if it validated the
literal input"**: a CI linter that checks a build artifact after a post-processing step silently
rewrote it, a form validator that runs after a normalization pass strips the very character the
validator is checking for, a signature check computed over a payload after a logging wrapper
appended a trailing newline. In every case, two features were each correct in isolation, and the
bug lives entirely in an ordering interaction neither feature's own tests would ever exercise,
because neither feature's tests knew the other existed.

The tell, in hindsight: the error message and the visible input never agreed, and re-reading the
input harder never would have found it — the fix required reading the *tool's* transformation
logic, not re-reading what was typed.
