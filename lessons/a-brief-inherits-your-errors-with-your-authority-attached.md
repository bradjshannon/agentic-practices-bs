# A brief inherits your errors with your authority attached

**Symptom.** A delegated agent was asked to install a Let's Encrypt certificate. It declined the
task outright, having spent its run reading docs and constructing a policy argument, with **three
tool calls and not one connectivity test**. The operator's reaction: *"wtf why did the agent not
verify"*. Ten seconds of measurement afterwards showed the premise it declined on was false.

**What actually happened.** The delegating agent had written this into the brief, verbatim:

> CRITICAL CONSTRAINT — the reason S3 is on ZeroSSL in the first place: **port 80 is NOT forwarded
> to S3**, so the standard HTTP-01 ACME challenge WILL FAIL. Do not burn time on it.

That claim was lifted from a project doc and never re-tested. Port 80 was in fact **open and
reachable**, answering from the target's own web server. The subagent behaved correctly given its
instructions: it was told the path was closed *and explicitly told not to spend time checking*, so
it didn't. The failure was authored entirely upstream, in the brief.

**The rule.** **Re-derive a claimed blocker before writing it into a brief — and never phrase an
unverified constraint as a prohibition.** A delegator's uncertainty does not survive delegation:
"the doc says X, verify it" and "X is true, don't waste time on it" produce completely different
agents. When passing along a constraint you have not personally measured, say where it came from
and instruct the agent to test it. Prohibitions are for things you know.

**Why it generalises.** Delegation launders provenance. A hedged, second-hand belief in the
delegator's head arrives in the subagent's context as a flat assertion from an authoritative
source, with no way to tell a measured fact from a copied one — and the subagent has *less*
standing to challenge it than the author did. Every layer of delegation strips another qualifier,
so a stale line in a doc becomes, three hops later, an unquestionable law that halts real work.
This compounds with the ordinary staleness of documentation: the older the doc, the more likely
the claim is wrong *and* the more authoritative it looks.

**The tell.** An agent that returns a well-argued refusal having run almost no commands is usually
reporting a defect in its brief, not in the task. Before accepting the refusal, check the premises
you handed it.
