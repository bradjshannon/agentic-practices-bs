# Fix the class, not the list — a list-shaped fix fails on the next member

**Date:** 2026-08-14 · **Domain:** defect remediation · **Cost:** the same defect recurred in front
of retail buyers the day after it was "fixed", on the server that had the fix

## Symptom

A product bug: a **fan** appliance referred to itself as an **air fryer** in its spoken replies. A
tester reported it. It was investigated, six source files carrying air-fryer wording were found and
corrected, the fix was deployed and verified live, and the issue was recorded as fixed.

**The next day the fan said "Voice control is now turned on for your air fryer" to a room of retail
buyers**, on the very server that had received the fix. The senior buyer asked why the product did
not know what it was.

## What actually happened

The defect was a **class**: "product-specific wording reachable by the wrong product." The fix was
applied to a **list**: the six files someone found that afternoon.

There were more. A later sweep — searching every language variant (`air fryer`,
`freidora`, `friteuse`, 空气炸锅) across the whole plugin and core tree rather than a known file
list — found further instances immediately, including in tool descriptions never examined the first
time and non-English strings in a file whose English string *had* been corrected.

The first fix was not careless. It was verified: deployed, container restarted, strings confirmed
live. **Every verification step passed, because each one verified the list.** The postcondition
checked was "are those six files fixed", and they were. The postcondition that mattered was "can a
fan still say air fryer", and nobody asked it.

## The rule

**When a defect is an instance of a pattern, the fix and its verification must both be expressed as
the pattern, not as the instances you happened to find.**

In practice:

- **Search for the pattern, not the known sites.** If the bug is a string, grep the string — and
  its translations, its casing variants, its hyphenations — across the whole tree.
- **Write the postcondition as the class.** "Zero occurrences of X reachable by Y" is checkable and
  survives new code. "Those six files are fixed" is true forever and means nothing.
- **A list-shaped fix should be a deliberate, stated choice**, with the residue named: "fixed these
  six; did not sweep; other instances likely." That is honest and lets someone finish it. Silently
  presenting a list fix as a class fix is what closes the ticket.

## Why it generalises

This is the remediation-side twin of a well-known measurement failure. Everyone knows a test that
asserts specific values passes while the general property is broken. The same thing happens to
*fixes*, and it is harder to see, because a list fix produces genuine green evidence for every
element of the list.

The tell is the shape of the bug report versus the shape of the change: a report that says "the fan
called itself an air fryer" describes a behaviour; a change that says "edited six files" describes
an inventory. **Whenever the change is an inventory and the bug is a behaviour, ask what enumerated
the inventory** — and whether that enumeration is guaranteed complete or merely what one person
found before they stopped looking.

Related shape worth naming: a *class* fix also needs a guard, or the class refills. Six strings were
corrected; nothing prevents the seventh being written tomorrow. A lint rule or test asserting the
class property is what converts a fix into a fix that stays.

## Related

- `lessons/verification-and-evidence.md`
- `lessons/a-guard-is-broken-until-you-watch-it-block-something-2026-08-14.md`
