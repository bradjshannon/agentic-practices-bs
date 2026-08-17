# Negating one disjunct does not negate the predicate (2026-08-17)

## Symptom

A mechanism built specifically to stop a status card from claiming the operator's attention was
shipped, tested, verified against live data — and the very first card it was used on came straight
back marked **YOUR TURN**.

## What actually happened

A status page decides "is this card waiting on the human?" with a predicate that is a **disjunction**:

```python
if not (entry.get("command") or entry.get("needs") == "decision"):
    return False
```

Two independent signals. A card is actionable if it poses a fork (`needs`), **or** if it carries a
shell command the human is being asked to run (`command`).

The operator had complained that cards kept claiming his turn after he had already answered them —
`needs` was a one-way door with no retraction path. So the fix added one: an append-only override
that could set `needs` back to null, with tests, a fold-in at every read site, and a live
verification showing the headline count drop.

All of that was correct. It was also only **half the predicate**. Applied to a real card, the
result was `needs=None` and still `needs_you=True`, because that card also carried a `command`: an
obsolete SQL `UPDATE` whose target row no longer existed. The card had gone on asking the operator
to run something that would have matched zero rows.

The tell was not subtle — but it was only visible because the card's state was **read back after
the edit** rather than assumed from the tool reporting success. The tool did succeed. It did
exactly what it was built to do. What it was built to do was insufficient.

## The rule

**When you build a mechanism to falsify a condition, enumerate every term that can make that
condition true — then check your mechanism against the predicate, not against the term you were
thinking about.**

A retraction, an opt-out, a suppression, a kill switch, an "acknowledge" — all of these are
negations of a predicate. If the predicate is `A or B or C`, a mechanism that clears `A` has not
retracted anything; it has narrowed the reason. The user-visible behaviour is unchanged, which
makes it *look* like the mechanism is broken when in fact it is incomplete.

Two practical consequences:

- **Read the predicate's source before building its inverse.** Not the docs, not the field name —
  the boolean expression. The field you were asked about is rarely the whole condition.
- **Give the retraction the same scope as the predicate, and say so in its name.** Here the flag
  was redefined from "clear the needs field" to "this card no longer asks for anything", and it
  clears both signals on one record — because splitting them across two operations would let a
  future caller clear one, see no change, and conclude the mechanism was broken.

## Why it generalises

This is the inverse of the more familiar "a green signal is not the thing it measures". The
familiar failure is a check that passes without exercising the capability. This one is a **fix that
applies without changing the outcome** — and it is harder to catch, because the fix genuinely
works, its tests genuinely pass, and the only thing wrong is the boundary of what it covers.

Anywhere a system computes "does this need attention" from several independent inputs — alert
suppression, notification muting, unread state, feature gating, permission denial — the same shape
is available. Silencing the loudest input and shipping is the default mistake.

The cheap defence costs one command: **after applying the mechanism, re-evaluate the predicate on
the real object and assert the outcome flipped.** Not the field. The outcome. If the mechanism had
been verified only against its own unit tests — which passed — this would have shipped, and the
operator's original complaint would have survived the fix that was built to answer it.
