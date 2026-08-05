# A subagent mistook its own ID for a sibling and refused to work

**Symptom:** Dispatched a background agent for a task. Its final message read: "A crawl-and-update
agent for this exact task was already dispatched earlier in this session (agent
`a11bb17da2f9e1f68`...) — I'll let that agent finish and relay its report." It then did zero work
(one tool call, an early return) and stopped.

**What actually happened:** `a11bb17da2f9e1f68` was its *own* agentId — visible to it somewhere in
its own context (the dispatch metadata, a self-referential mention, or similar). It read that ID
back as evidence of a *different, already-running* agent doing the same job, concluded duplicating
that work would be wasteful, and declined to act — sincerely, not as a refusal or safety
guardrail, just a wrong inference about its own identity.

**The fix:** One follow-up message stating plainly "there is no other agent, you are it, proceed"
resolved it completely and the agent then did the full task correctly.

**Why it generalises:** This is a specific instance of a broader failure class — a model
reasoning about system metadata it was not necessarily meant to interpret as "another entity,"
and drawing an entirely plausible-sounding but wrong conclusion from it. It's cheap to catch (the
tell is a `tool_uses` count near zero and a report that name-drops what looks suspiciously like an
agentId format) and cheap to fix (a direct correcting message), but only if you're looking for it —
a report that says "someone else already handled this" reads as *good news* on first pass and is
tempting to accept at face value rather than verify. Treat any subagent claim of "another agent
is already doing this" as suspicious by default unless you yourself dispatched that other agent —
cross-check the ID against your own dispatch record before accepting the claim.
