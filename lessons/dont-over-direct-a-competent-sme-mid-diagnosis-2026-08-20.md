# Don't over-direct a competent SME once it has demonstrated competence mid-task

**Symptom:** a coordinator kept prescribing exact diagnostic steps to a dispatched agent that was
actively root-causing a hard hardware bug — which tool to run, which theory to chase, what to try
next — even after the agent had already independently found and fixed two real, verified defects
earlier in the same investigation. The operator: "stop giving stupid instructions to the SME and
let it do its job."

**What actually happened:** two of the coordinator's own theories about the underlying cause
(injected into the agent's brief as prime suspects) were wrong — the agent's own decoded backtrace
found the real cause faster and more precisely than either inference. After the correction, the
coordinator switched to handing the agent raw data (a log file location) and letting it choose the
next step; the agent proceeded to root-cause and fix the actual bug in that same pass.

**The rule:** the right amount of direction to a dispatched agent is inversely proportional to how
much it has already demonstrated it can drive itself. A first dispatch benefits from a detailed
brief (goals, constraints, what "done" looks like) because the agent has no track record yet. A
second or third dispatch on the SAME investigation, after the agent has already produced real
findings, should shrink to: here's new data, here's the open question, your call. Continuing to
prescribe tactics past that point is not extra safety — it substitutes the coordinator's weaker,
less-informed inference for the agent's stronger, more-informed one, and the coordinator usually
doesn't notice this is happening because prescribing detailed instructions *feels* like diligence.

**Why it generalises:** this is the delegation-trust curve, and it applies to any dispatched
worker (subagent, contractor, junior engineer) mid-task — the failure mode is not "delegate too
little," it's "delegate once, then quietly re-centralize control via increasingly specific
instructions once you're anxious about the outcome." The fix is procedural, not attitudinal: after
an agent's first real independent finding, deliberately shift briefs from prescriptive ("do X then
Y then Z") to data-plus-question ("here's what's new, your call").
