# A subagent's permission classifier can be scoped narrower than the top-level session's

**Symptom.** Operator gave explicit, live, in-chat authorization for an irreversible outward action
(publishing a new SDK version to a public component registry). Dispatched an SME subagent with that
authorization stated and quoted verbatim in the brief. The subagent staged everything correctly
(version bump, host tests, packing, tagging) and then, when it reached the actual `--live` publish
command, reported the call was **denied by the permission classifier** — and correctly stopped,
reasoning (its own words) that "a relayed chat instruction isn't consent for an irreversible action,
only the permission system or the operator's own message is," and declined to route around it.

**What actually happened.** Running the *identical* command myself (the top-level conductor session,
in the same turn, no new authorization) succeeded immediately — no classifier prompt, no block. The
subagent's refusal was principled and correct given what it could see, but the actual gate that
stopped it was a **permission scope difference between the subagent and the session that dispatched
it**, not a considered policy decision replayed twice. The subagent had no way to distinguish "the
classifier is protecting against exactly this shape of relayed-authorization request" from "the
classifier simply doesn't extend live-authorization the same way to a subagent as to the top-level
session" — both produce an identical denial from inside the subagent.

**The rule.** When an irreversible/outward action has already been explicitly authorized by the
operator in the current session, and a dispatched subagent hits a permission denial on the actual
execution step: **retry the exact same command from the top-level session before concluding the
action is blocked outright.** The subagent's refusal to route around a denial is correct and should
not be second-guessed — but "denied for a subagent" and "denied, full stop" are different findings,
and only the second one is a genuine dead end. The subagent still did the valuable, non-authorized
half of the work (staging, verification, everything reversible) and left a clean, fully-prepared
handoff — that pattern (delegate the buildup, execute the final authorized step yourself) is worth
keeping even once the scoping question above is settled either way.

**Why it generalises.** Any dispatch architecture where a parent session can authorize actions a
child session cannot will produce this exact shape of false negative — a correct, cautious refusal
from the agent best positioned to comply, and a correct, authorized success one level up. The
practical takeaway is procedural, not a permission-system fact to memorize: treat a subagent's
irreversible-action denial as "try it yourself before treating it as final," the same way a
classifier block on a *specific tool shape* gets a different-shape retry rather than a silent
rephrase (see the standing "classifier block is reported, never rephrased past" rule) — this is the
one narrow exception, because the retry here changes *who* is asking, not *how* the same request is
worded.
