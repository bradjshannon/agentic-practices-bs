# `SendMessage` is a non-destructive liveness probe; `TaskStop` answers less and costs more

**2026-08-01.** A conductor killed a healthy subagent to find out whether it was alive. It
already had the answer, in a tool result it had read twenty minutes earlier and dismissed as
bookkeeping.

## The measurement

Sending a message to a subagent returns a different string for each state, and **none of them
disturbs the agent**:

| state | reply |
|---|---|
| running right now | `Message queued for delivery to <id> at its next tool round.` |
| finished / idle | `had no active task; resumed from transcript in the background` |
| previously killed | `was stopped (killed); resumed it in the background` |

`TaskStop` distinguishes only *exists* from *doesn't*, and it does so by ending the agent. It has
one residual use: it prints the list of agents that ARE running, so it is a census — but only
reach for it when you actually mean to stop something.

## What happened

A firmware lot had run ~2h with no commit, no branch, and no change to the boards. The conductor
checked the process table for a running `esptool`/`ninja`, found none, concluded "dead", and ran
`TaskStop`. The agent was mid-build; its last line was *"Let's build the host image on this
branch."*

The disproof was already in hand. A `SendMessage` sent earlier had returned `queued for delivery at
its next tool round` — a string only a live agent produces. It was read as delivery bookkeeping
rather than as evidence about the subject.

Revival recovered it (`SendMessage` resumes a killed agent with its context intact), so the cost was
time, not work.

## Two rules

1. **If you have anything to say to the agent, say it — that message is both the probe and useful
   work.** "Commit what you have" is a better probe than a kill, and it improves the situation
   whichever state the agent turns out to be in.
2. **Absence of a process is not absence of an agent.** A subagent between tool calls, or waiting on
   a slow one, shows nothing in the process table and writes nothing to disk.

## The upstream error, which is the one worth fixing

The brief for that lot required no progress reporting. **Two hours of legitimate slow work and a
wedge are indistinguishable from outside**, because a subagent has exactly one channel: its final
message. No probe fixes that; only the brief does.

So: **every brief containing a slow step must require a milestone line at each real checkpoint** —
first build green, artifact flashed, each observation made — and must say that if a step will take a
long time, the agent should say so *before* starting it, not after. Silence is not a report, and the
right response to a silent agent is a message, not a kill.

Related: `handing-off-work-that-is-still-running.md`, `a-subagents-negative-is-not-evidence.md`,
`instrument-silence-not-data`.
