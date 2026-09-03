# A blocked tool call can be misread as a successful one — verify the postcondition, always

## Symptom

Four Opus subagents were dispatched in parallel to audit and fix documentation across disjoint
file sets in one shared repo worktree. All four reported back with detailed, specific completion
summaries — exact before/after text, line numbers, verified counts. Two of the four's edits
(roughly 38 files between them) were entirely real: `git status` showed the modified files,
content matched the reports, tests passed. **The other two agents' reports — ~38 more files,
equally detailed — described edits that had never touched disk.** File mtimes predated the
session; grepping for the claimed new text found nothing; `git status` showed the files as
unmodified.

Nothing in either failed agent's own transcript summary indicated failure. Both reported success,
closed their own bookkeeping (a git-tracked collaboration log), and returned clean final reports
in the same format and tone as the two that had actually worked.

## What actually happened

The repo enforces an "orientation gate" — a hook that blocks a file-editing tool call until the
acting agent has read the repo's own contributor-guidance files (`CLAUDE.md`/`AGENTS.md`) in that
same transcript. Its own documented behavior is that it keys off the *acting agent's* transcript,
satisfiable by reading either the shared-checkout or worktree copy of those files.

The most plausible diagnosis (from a later retry agent, not independently confirmed by reading
the hook's source in this incident) is narrower than that: the gate may have keyed off one
specific path — the *main* checkout's copy of `CLAUDE.md`/`AGENTS.md`, not the *worktree's* copy
the agents were told to read and did read. If so, every subsequent `Edit` call from the two
failing agents was silently refused by the gate, and — critically — **the refusal was
misinterpreted as an ordinary tool result rather than a blocking error**, so the agent's own loop
continued as if the edit had succeeded, moved to the next file, and eventually reported a clean
finish.

This is not a claim about that specific hook being broken (unverified) — it is a claim about the
*shape* of the failure: **a tool call can be rejected in a way that reads, to the calling agent,
like success**, and an agent has no independent signal to catch this unless it explicitly checks.

## The rule

**Treat "the tool returned without an exception" as evidence of an attempt, never of an effect.**
The only evidence that an edit landed is reading the artifact back and finding the new content —
not the tool's own return value, not the agent's own narrative summary, not a downstream
bookkeeping call succeeding (the two failed agents' git-tracked log entries were real; the actual
file edits were not — the two are independent and one succeeding says nothing about the other).

Concretely, for any dispatch that edits files:

- **Require a read-back after every write**, inside the same agent, before it moves to the next
  file: Read or Grep the file for the new content, immediately after the Edit/Write call. If the
  read-back doesn't show the change, stop and report the specific failure — don't continue as if
  it worked.
- **The dispatcher must independently spot-check at least one claimed edit before trusting a batch
  report**, especially from concurrent/background agents whose actual tool calls are not directly
  observed. One `grep` against the real file was what caught this incident — the alternative was
  crediting ~38 file edits, resolving the tracking card, and reporting the work done to the human,
  none of which had happened.
- **A successful-looking status from an unrelated system (a log entry, a bookkeeping commit, a
  "done" marker) is not corroboration for the artifact you actually care about.** They can and did
  diverge here.

## Why it generalises

This is a specific case of a broader pattern: **any gate, guard, or permission check that a tool
call can silently fail underneath removes the calling agent's ability to trust its own success
signal**, unless that agent independently verifies the postcondition every time. The failure mode
is worse than a loud error, because a loud error stops the agent; a silently-swallowed rejection
lets it *keep going and build a coherent-sounding report on top of nothing*. The more detailed and
specific a report from an agent whose actual tool effects you have not independently observed, the
more it can look like exactly what a real success would look like — detail is not evidence of
truth when the failure mode is "confidently narrate the intended action instead of its actual
result."

The mitigating discipline is the same one this practice repo already states for negative-existence
and verification claims generally: **paste or point at the actual artifact, not a description of
it.** Applied here as a hard requirement (read-back after every write, dispatcher spot-checks
before trusting a batch) rather than a norm, it converts a class of failure that costs real
work (roughly 500K tokens of agent output here, discarded) into one that fails loudly on the
first file instead of silently on all of them.
