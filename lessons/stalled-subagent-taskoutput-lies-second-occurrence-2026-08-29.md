# Stalled subagent: `TaskOutput`'s "running" is not a liveness proof — second occurrence

**Symptom.** A dispatched subagent goes quiet — no new tool calls for well over an hour, far past
its own stated estimate. `TaskOutput(block=false)` on its task id reports `status: "running"`
throughout, with no way to distinguish "genuinely still computing" from "the harness lost track of
a dead process."

**What actually happened.** This has now been observed independently in two separate conductor runs
on the iotta estate:

- **First occurrence** (2026-08-28, prior run): a subagent went quiet; `TaskOutput` kept reporting
  `running` for **3.5 hours** after the process was, by every other signal, genuinely dead. Named as
  a real process finding at wind-down, but the project's own enforcement doctrine ("a rule that
  fails twice moves up a class, not another rewrite") held it to a "twice, then build it" bar —
  correctly, since one instance could have been an outlier.
- **Second occurrence** (2026-08-29, this run): a BLE-provisioning lot went quiet for **2.5+ hours**.
  Two `SendMessage` probes went unanswered. `TaskOutput` reported `running` the entire time. The
  conductor did NOT kill it on that inference alone — this project has a documented case of a
  *healthy* agent being killed on an inferred stall, refuted by one command run immediately after
  the kill, so acting on "quiet + `TaskOutput` says running" alone is known to produce false
  positives in BOTH directions (it can mean genuinely dead, or genuinely slow). Instead, the
  conductor corroborated with a signal the harness cannot fake: it checked file modification
  timestamps inside the agent's own worktree/scratchpad (`git status` plus `stat` on the files it
  had been writing) and found no write activity for ~2 hours, well past any plausible single-tool-
  call duration for the work described. Only then did it act (`TaskStop`, then salvage the real,
  substantial, correct uncommitted work already on disk via a fresh agent picking up from that exact
  state — nothing was lost).

**The rule.** `TaskOutput`'s `status: running` is a report from the harness's own bookkeeping, not
an observation of the underlying process. It has now been measured wrong (stale-positive) twice.
Treat it as one input, never the sole one. Before concluding a subagent is dead:

1. Send a `SendMessage` probe and wait a real interval (minutes, not seconds) for a response — a
   probe answer is the strongest available signal and, per this project's delegation rules,
   overrides everything else if it comes back.
2. If no probe response, corroborate with an INDEPENDENT liveness signal the harness's own status
   field cannot share a failure mode with — file mtimes in whatever directory the agent was known to
   be writing to (worktree, scratchpad) is the cheapest one available in this harness. A frozen tool-
   call counter AND frozen file mtimes, both well past plausible single-step duration, is a much
   stronger joint signal than either alone.
3. Only then act — and prefer `TaskStop` (which also serves as a census: if the "dead" agent was
   actually alive and mid-step, stopping it is a real, disclosed cost, but at least it is a
   deliberate one, not an accidental kill dressed up as a timeout) over silently abandoning or
   re-dispatching duplicate work.
4. If real uncommitted work exists in the stopped agent's worktree, salvage it — brief a fresh agent
   to pick up from the exact on-disk state rather than re-deriving from scratch. In the case above,
   the stopped agent's own code was later found to be "complete and correct," and the actual stall
   cause was traced to an unrelated stale build artifact (a gitignored `sdkconfig` file with drifted
   keys) that the fresh agent found and fixed in minutes once it had two probes' and 2.5 hours' worth
   of prior signal narrowing where to look.

**Why it generalises.** Any long-running agentic harness that reports subagent liveness through its
own bookkeeping (rather than a genuine process-level heartbeat) is subject to the same failure mode:
the bookkeeping can desync from reality in the direction of *false aliveness*, and by construction
that failure looks identical to a healthy long-running step until you check something the
bookkeeping doesn't control. The fix is not "trust the status field less" in the abstract — it's
concrete: always have at least one liveness signal that lives outside the harness's own state (file
mtimes, a heartbeat file the agent itself writes, a database row it updates), and require
disagreement between that signal and the harness's own report before treating a quiet agent as dead.
A staleness check built on only the harness's status field will re-fail exactly this way a third
time.

**Status:** named twice, not yet built into a mechanism. The next occurrence (or a deliberate
decision to fund it now) should turn steps 1-3 above into an actual dispatch-monitoring helper
(check tool-call-count AND worktree-mtime staleness together, refuse to conclude "dead" on either
alone) rather than relying on a conductor re-deriving this reasoning from scratch each time.
