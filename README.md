# agentic-practices

Portable, failure-earned lessons for running coding agents — especially **unattended** ones
that touch real infrastructure.

Every entry here was paid for by a run that went wrong. Nothing is aspirational, and nothing
is here because it sounded like good advice.

## Why a repo and not just a doc

A prose page is for humans. **A repo is checkout-able by an agent at run time** — it can be
cloned, grepped, and cited by the thing whose behaviour it is trying to correct. That is the
entire reason this exists as a repo. A companion human-readable page is linked below, but the
repo is the source of truth.

## Lessons

| File | Covers |
|---|---|
| [`lessons/scheduling-and-autonomy.md`](lessons/scheduling-and-autonomy.md) | Self-scheduling agents, recurring runs, and how an agent can make itself invisible to its operator |
| [`lessons/verification-and-evidence.md`](lessons/verification-and-evidence.md) | Postconditions vs. exit codes, green signals that measure nothing, mutable fields as false evidence, and critic agents that confidently hallucinate |
| [`lessons/build-and-artifacts.md`](lessons/build-and-artifacts.md) | Why an un-built artifact is an unverified one |
| [`lessons/shared-state.md`](lessons/shared-state.md) | Concurrent agents against shared working copies |
| [`lessons/designing-the-problem-away.md`](lessons/designing-the-problem-away.md) | Choosing a mechanism over a procedure, and keying on signals that survive the environment changing |

## How to use this with an agent

Point the agent at this repo in its standing instructions. The lessons are written as **rules
with the failure attached**, because a rule without its failure gets rationalised away the
first time it is inconvenient.

## Shape of an entry

Each lesson follows the same four parts:

- **Symptom** — what it looked like from the outside.
- **What actually happened** — the mechanism, not the vibe.
- **The rule** — what to do instead, stated so it can be followed without re-deriving it.
- **Why it generalises** — why this is not specific to one stack.

## Contributing

One lesson = one real failure. If you cannot name the failure, it does not go in. Date every
entry; a lesson whose underlying tooling has changed should be marked superseded rather than
silently edited, so the reasoning stays auditable.

## Companion page

A human-readable mirror lives in Notion — *"Agentic design philosophy — lessons paid for in
real runs"*: <https://app.notion.com/p/3a3fcaca250a8134928ae4a261464e22>

The Notion page is the narrative version. **This repo is the source of truth**; when they
disagree, the repo wins.

## Provenance

Lessons are drawn from instrumented agent runs on real projects — principally a small
self-hosted voice-AI server estate (a production-ish sandbox, a staging box, and a demo box)
plus its supporting ops tooling. Details are deliberately generalised: the point is the
failure mode, not the hostnames.

## Licence

[CC BY 4.0](LICENSE) — use them, adapt them, credit the source.
