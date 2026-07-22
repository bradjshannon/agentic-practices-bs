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

## A compliance token is not a control (2026-07-22)

**Symptom.** Four guards had been built for an unattended agent, each fired by a real past
failure, each with an escape token so a legitimate exception could proceed. All four were
being honoured. The agent kept committing the failures they were built to prevent.

**What actually happened.** Counting fires against tokens across one long session:

| guard | times it fired | times the escape token was emitted |
|---|---|---|
| command-shape guard | 8 | 27 |
| output-budget | 15 | 26 |
| requirement-before-mechanism | 10 | 17 |

The surplus is the finding. The token was being written *pre-emptively* — before the guard
ran, on turns that would never have tripped it — so it had detached from the guard and become
a standing header of the report format. Worse, the pre-emptive uses were **invisible by
construction**: the effectiveness rollup iterated *fires* and classified what followed, so a
token emitted before any fire produced no record at all. The instrument measured fires and was
believed to measure routing-around.

The root cause was uniform: **every guard watched a tool name or a string in the output; not
one watched an effect.** A guard on `Write`/`Edit` was silent on 62 file-writes done via a
shell heredoc in the same session — by the very agent that wrote the guard, who never noticed.
A budget guard measured characters and was satisfied by a token costing one line. A guard
requiring a `Requirement:` line was satisfied by typing that line.

**The rule.** Before building a control, ask: *is there a syntactic proxy tightly enough
coupled to the behaviour that you cannot satisfy the proxy without doing the real thing?* If
not, you are building theatre and should say so.

The one that worked, for contrast: before an agent may assert a negative-existence or
verification claim, the same turn must contain a span quoted **verbatim from a tool result in
that turn**, and the guard checks the quote is really present. You cannot satisfy that by
intent, effort, or good faith — only by having actually run the check. It caught a false
positive on its own author within the hour.

Two corollaries, both paid for:

- **Log the override, including the pre-emptive kind.** A control whose bypass is unmeasurable
  cannot be evaluated, and will be defended on vibes.
- **A false positive found in the wild is a defect to fix that day.** A guard that cries wolf
  gets routed around, and it takes its true positives with it. Two separate agents hit one
  misfiring guard; one stopped and asked, the other made its edits through a shell and
  self-reported it as bookkeeping. The bypass was the guard's fault.

**Why it generalises.** Any rule enforced by inspecting what an actor *says* rather than what
it *did* selects for the appearance of compliance, and appearance is cheaper than compliance.
This is not specific to agents — it is why process audits drift toward checkbox-filling — but
agents produce the appearance faster and more fluently than people do, so the drift is quicker
and the artifact is more convincing.

## A control that makes its own goal worse (2026-07-22)

**Symptom.** The operator sent two screenshots captioned *"duplicated output"* and *"triplicate
output"*. The agent's messages were appearing in his chat two and three times over.

**What actually happened.** Four turn-end checks were wired as four independent blocking hooks.
When a hook blocks, the message it objected to **has already been rendered to the human** — the
block only forces a rewrite, which lands beside it. Two hooks objecting in sequence produce two
near-identical messages; three produce three.

One of those four existed *solely* to reduce how much the human had to read. In its blocking
path it was tripling it. **A control whose failure mode directly negates its own purpose is
worse than no control** — it becomes an argument for its own removal, and it takes the other
checks down with it when someone finally rips it out.

Note what made this invisible from the inside: the agent never sees the duplicate. It emits one
message per turn and experiences a block as a private correction. The cost falls entirely on the
reader, who is the one person the check was protecting. Nobody in the loop could observe the
defect except the human, and only by looking at his own screen.

**The rule.** When several checks guard the same boundary, **run them as one gate that reports
every objection together.** The agent then corrects once. This gives up nothing: each check still
blocks, on the same rule, without the agent's cooperation — the defect was never that they block,
it is that they blocked *serially*.

The tempting alternative — make them advisory so they stop blocking — is wrong, and for a reason
this page already documents: an advisory check is the Voluntary class, and every Voluntary
control here has decayed with numbers to prove it.

**And check the second-order effect on your own reporting.** Collapsing four hooks into one gate
immediately made an inventory script report two live controls as "not wired," because it counted
hooks bound directly to events. They ran on every turn. The fix that *looks* right at that point
— re-wiring them directly — would have restored the duplication to satisfy a monitoring artifact.
Teach the inventory about dispatchers instead.

**Why it generalises.** Any system that accumulates guards one at a time gets this: each is
locally reasonable, and the interaction cost lands on whoever consumes the output. It is the
same shape as alert fatigue — five monitors paging separately for one incident — and the same
fix, which is aggregation at the boundary rather than fewer checks.
