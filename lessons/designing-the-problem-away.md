# Designing the problem away

Lessons about choosing a *mechanism* over a *procedure*, and about picking the signal that
survives the environment changing underneath it.

---

## Prefer structural safety to procedural safety

A rule engine was being designed for a system where a bad rule could physically start a
heating appliance. The instinct was to reach for the heaviest control available: permission
tiers, an approval chain, an audit trail.

The operator rejected all of it — one person, a demo fleet, no real users. The governance
would have cost more than the risk it managed, and it would have been the first thing
abandoned under deadline.

What replaced it was cheaper *and* stronger, because it does not depend on anyone following
a process:

- **Route through the confirmation that already exists** rather than inventing a new gate.
  The best approval step is one the end user already sees.
- **Constrain by construction.** Tool names come from the real tool surface, never free text;
  arguments clamp to their declared domains. *A rule that cannot express an unsafe action does
  not need approving.*
- **Make reversal cheap instead of entry expensive.** One toggle disables a rule and the
  system falls back to its previous behaviour. When there is one operator, cheap rollback beats
  prior review — the review is the same person, five minutes earlier, with less information.
- **Let the existing artifact be the audit trail.** Rules export to version control, so history
  is free rather than a subsystem.

The question to ask before proposing any control: *what does this control cost here?* An
enterprise shape imported into a two-person project is not caution, it is overhead that will
be discarded — leaving nothing.

> **Caveat learned the hard way:** verify what the "existing confirmation" actually does before
> routing through it. In this case the guard turned out not to be a confirmation at all — it was
> a *failure catcher* that fires only when no tool call was produced. Building on a mechanism you
> have not read is how a safety argument becomes decorative.

## Key on the event, not on the payload

A device was supposed to trigger a canned response when it woke. The obvious implementation
matches the wake phrase in the text the device sends.

That implementation is quietly wrong, and the reason generalises. The wake phrase is a
compile-time constant that differs across firmware variants, and the fleet was running several.
Matching the text would have worked for the minority of devices whose literal happened to be in
the server's list, and silently failed for the majority — while being reported as a fix.

The device emits a *distinct message type* on wake. Its firmware calls the send function from
exactly one place, so the message type alone is unambiguous. **Keying on the event rather than
the payload made the rule immune to the variation**, and needed no per-version table.

The general shape: when a system offers both a structural signal (a message type, a channel, a
callback) and a content signal (a string to parse), the structural one usually survives changes
the content one does not. Prefer it — then use content only for the residual ambiguity the
structure genuinely leaves.

Here the residual was real: other clients used the same message type as a general text channel,
so the rule still needed a discriminator. But that discriminator only had to answer "is this a
real device?" — a far weaker and more stable question than "which of N wake phrases is this?"

## Find the one call site before believing the abstraction

Establishing "this message can only mean a wake" took a single grep for the emitting function's
call sites: one, in the wake path. That is a stronger guarantee than any amount of reasoning
about what the message *usually* means.

Conversely, an earlier investigation concluded a system had no deterministic shortcut, having
traced a request into a function named for the slow path and *assumed* the name was accurate.
The shortcut lived inside that function. Read the callee; do not infer behaviour from a name.
The distinction is between "the string is not in this file" and "the mechanism does not exist" —
they look identical in a search result and mean entirely different things.
