# An omitted `model` inherits the expensive parent, on every agent in the fan-out

**2026-08-15.** A conductor launched a 4-mechanism build workflow — draft, adversarial
review, refine — and omitted `model` on all three stages, which the tool's own guidance
calls the correct default. **All 11 workflow agents ran the top-tier model.** The operator
caught it from outside: *"hey why are you using opus models for every step of the workflow?
that's crazy ... this is so wasteful"*.

Measured, not inferred: `grep -o '"model":"[^"]*"'` over the run's agent transcripts returned
`64 "model":"claude-opus-5"` on the first file sampled, and the same on the rest.

## Why the default is a trap here

The contract says an omitted `model` means the agent **inherits the main-loop model** — the
resolved session model, not a cheap floor. That is a sane default when the parent is cheap. It
is exactly wrong when the parent is the expensive tier, which is precisely when a fan-out is
most worth doing, because the whole point of the architecture is that an expensive orchestrator
spends its judgment on the *briefs* while cheap workers do the work.

So the failure has an inverted shape: **the more deliberate you were about running the
orchestrator on a strong model, the more the default costs you.** Nothing announces it. The
run completes, the results are good, the bill is silent, and the only signal is a human
noticing the model names.

## It is not limited to the workflow tool

The same inheritance applies to the plain agent-dispatch tool: a dispatch to an agent type
whose definition pins no model inherits the parent too. Catch-all types (`general-purpose`,
`claude`, or whatever the local equivalent is) are exactly the ones with nothing pinned, so
they are the ones that silently ride the expensive tier. Types with `model:` in their own
definition file are unaffected — which is why a project can look correctly configured while
half its dispatches are not.

## What to do

- **Pin the model explicitly on every stage of a fan-out**, at the top of the script, with a
  comment saying why. Do not rely on the default, and do not rely on remembering.
- **Pin it on catch-all agent dispatches too**, or give the catch-all types a model in their
  own definitions so the dispatch site cannot get it wrong.
- **Raise a single stage deliberately** if one genuinely needs judgment, and say so in the same
  edit — a per-stage exception with a stated reason is the point; a blanket inherit is not.
- **The check that finds it after the fact:** grep the run's agent transcripts for the model
  field. Per-agent metadata files may carry nothing useful (`agentType`/`spawnDepth` only), so
  the transcript is the instrument.

## The general form

A default that reads as "unset" is often "inherit", and inheritance flows from whatever the
caller happens to be. Any per-call knob left unset in a fan-out multiplies the caller's setting
by N. Before fanning out, ask what each unset field will resolve to — the answer is rarely
"nothing".
