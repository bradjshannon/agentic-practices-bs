# Delegating a task exports its stale premise, and the other agent cannot check it

## Symptom

An agent on one machine handed an agent on another machine a diagnostic probe: "test whether S3's
websocket endpoint is reachable over the WAN — my hypothesis is that it is blocked, use S1 as a
positive control."

The receiving agent did excellent work. It refused to execute an opaque blob arriving over the
channel, authored an equivalent probe itself, ran it from a genuine external vantage, caught a
trust-store discrepancy between two TLS clients on the same host in the same second, and returned a
careful result with its own limitations stated.

The blocker had been fixed four days earlier. Nothing it did could have discovered that.

## What actually happened

The sender's belief — "S3 may be unreachable from outside" — was true when formed and false when
sent. In between, a firewall rule had been opened and the original symptom had been confirmed
resolved. The sender never re-derived the premise before delegating; it delegated the *test* rather
than the *question*.

The receiver had no way in. It was handed a hypothesis and a method, and both were internally
coherent. Every check available to it — is the control valid, does the probe measure what it claims,
is my instrument trustworthy — it performed, and passed. **None of those checks can detect that the
question was already answered**, because staleness is not a property of the test. It is a property of
the world the test was written in, and the receiver was never shown that world.

The falsification, when it finally came, took one query against a log the sender had access to the
whole time.

## The rule

**Before delegating, re-derive the premise, not just the method.** The receiving agent will validate
your method rigorously and cannot validate your premise at all.

Practically:

- **Send the question, not just the task.** "Is S3 reachable?" invites the receiver to ask why you
  think it might not be. "Run this probe against S3" does not. The second form is faster and strictly
  worse, because it forecloses the only check that would have caught this.
- **State when you last verified the premise, and how.** A delegation carrying "as of <date> the
  symptom was X, verified by <method>" lets the receiver notice the date is old. A bare hypothesis
  carries no expiry.
- **Prefer the cheapest falsifier you own over the most rigorous one they own.** The sender could
  have counted records in a log in one command. Instead it commissioned a WAN probe on another
  machine. Rigour on the far side does not compensate for a question you could have closed locally.
- **When the receiver's careful work returns a null result, suspect the premise before the method.**
  A well-built instrument that finds nothing is evidence about the question, and "the question was
  stale" is one of the live explanations.

## Why it generalises

Any delegation — to a subagent, a teammate, a contractor, a ticket — transmits the task and the
assumptions in the same envelope, but only the task is legible on arrival. The receiver sees the
work; the sender's model of the world is invisible and therefore unauditable. This gets worse as the
receiver gets *better*: a diligent agent will exhaust every check inside the frame you gave it, and
report high confidence, precisely because it never questioned the frame.

The asymmetry is the point. **You can only check the premise before you delegate. Afterwards, nobody
can.** Which means the review that matters is not of their output; it is of your own belief, and it
has to happen first.

Corollary worth keeping: when the far agent's careful work is wasted by your stale premise, say so
plainly and immediately. The failure is a cheap lesson and an expensive silence — if they do not
learn the premise was stale, they will carry your conclusion forward as confirmed.

Related: `a-message-to-one-agent-can-kill-another.md`, `a-red-signal-deserves-the-same-suspicion-as-a-green-one.md`, `measure-the-instrument-before-the-effect.md`.
