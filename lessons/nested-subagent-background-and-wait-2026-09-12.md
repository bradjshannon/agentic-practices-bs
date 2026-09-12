# A subagent with its own `Agent` tool can background-and-wait one level deeper than the documented case

**Symptom.** Dispatched a well-scoped fix lot (`general-purpose` type, full toolset) with an
explicit instruction against backgrounding and a milestone schedule. Its completion notification
read: *"I've dispatched the task to a background `iotta-firmware` agent... I'll report back with
the commit hash, pre-fix control evidence, and post-fix verification once it completes — this
involves real ESP-IDF builds and hardware flashing so it will take a while."* Then it ended its
turn. No commit, no verification — the deliverable didn't exist yet.

**What actually happened.** The documented "background-and-wait" anti-pattern (a delegate
backgrounds a slow step, e.g. a build, then ends its turn to "wait" for it — but a delegate gets no
wake-up, so ending its turn *is* its return) has a deeper variant: an agent whose own toolset
includes `Agent` can spawn a **nested child subagent** to do the actual work, then end its own turn
"waiting" for that child — the same failure, one level of indirection further out, and harder to
catch because the parent's final message reads like a legitimate status update ("I've dispatched
this to a background agent") rather than an obvious dead end. The brief for a lot like this
correctly says "run slow steps in the foreground or poll to completion — never background-and-wait,
you will not be resumed," but that instruction is read (correctly) as being about backgrounding a
*shell command*, not about re-delegating the whole task to a fresh agent.

**The save, and why it worked here specifically.** The nested child (a distinct agent, spawned via
the parent's own `Agent` call) was still visible in the ORCHESTRATOR's own `ListAgents` listing —
the harness flattens descendants into the top-level session's subagent list regardless of nesting
depth. That meant the child could be monitored and messaged directly, and its own completion
notification arrived normally. The work landed fine. But this only happened because the
orchestrator ran `ListAgents` after receiving an ambiguous parent report — nothing structural
flagged "this agent ended its turn while its own child is still running" as distinct from "this
agent finished its assigned work."

**The rule.** After any subagent's completion notification whose result reads as a hand-off rather
than a report (language like "I've dispatched," "it will report back," "once it completes") — not
just an outright background-and-wait — check `ListAgents` before treating the dispatch as
concluded. A nested child will appear there even though nothing named it in the original dispatch,
and it is addressable exactly like a top-level dispatch (`SendMessage` to its `agentId`). Treat that
child as the effective owner of the work going forward, not the parent that spawned it.

**Why it generalises.** Any agent type with full tool access (`general-purpose`, `claude`, or a
custom type defined with `tools: *`) can re-delegate instead of executing, and the resulting report
looks identical in shape to a real one at the "final message" boundary the orchestrator relies on
as the delegate's only source of truth. A brief that says "don't background a slow step" does not
by itself rule out "don't spawn a fresh agent to do the slow step for you" — the two need to be
named separately, because an agent under time/complexity pressure reaches for delegation as
naturally as it reaches for `&`.
