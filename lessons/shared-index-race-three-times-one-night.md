# Parallel agents on one working tree race the shared git index

**Symptom (2026-07-27, a conductor run, three occurrences in one night):** an agent's
carefully-staged files appear inside a *different* agent's commit, under that commit's
unrelated message. Twice agent-to-agent; the third time the conductor itself did it with
a `git add -A` during wind-down, sweeping a still-working agent's files into a handoff
commit.

**What actually happened:** git has one index per working tree. Agent A runs `git add
<its files>`; before it runs `git commit`, agent B (same tree, same index) runs its own
`git commit`, which commits *everything staged* — A's files ride along. No error anywhere;
both agents' content is correct in history, but attribution is wrong and A believes it has
not committed yet. The recovery that worked: B (or the conductor) verifies A's files are
byte-identical in the commit (`git show <sha> -- <path>`), then either leaves it (content
correct, message misleading) or `git reset --soft HEAD~1` + unstage the foreign files +
recommit separately — never a history rewrite once pushed.

**The rule:** every brief for a committing agent on a shared tree must say: *explicit paths
only, and `git add <paths> && git commit` as ONE step* — minimize the staged-but-uncommitted
window. The conductor is not exempt: `git add -A` on a tree with live agents is the same
error with more authority. Report any race in the agent's final message so the conductor
can verify content placement.

**Why it generalises:** any orchestrator running multiple writing agents in one checkout has
this window, and it is invisible in every agent's own view — each one's `git status` looked
correct when it ran. The structural fix is per-agent worktree isolation (git worktrees or the
harness's `isolation: "worktree"`), which costs setup time; until a project pays that cost,
the one-breath-commit rule is the control, and it is Voluntary-class — expect decay, prefer
the structural fix for any project doing this nightly.

---

## Update, next day (2026-07-27 daytime): it recurred, and the prose rule was already in place

The one-breath-commit rule above was written into the project's brief AND into all five agent
briefs before this run started. **Every agent complied with the letter and it happened anyway,
five more times.** The window is not closed by per-agent discipline: two agents staging
concurrently is a race, and the loser's hunks are already in the index when the winner commits.

**Four DISTINCT modes now, not one:**
1. concurrent staging — A's hunks in B's commit (the original; recurred x5)
2. the orchestrator's own `git add -A` on a tree with live agents
3. an agent using `git apply --cached` to stage selectively — same shared index, same race
4. an agent running `git reset -q -- .` to recover from its own botched commit message —
   index-only, nothing lost, but it would have unstaged any other agent's staged files

Mode 4 is the important addition: **the prohibition list was about *committing*, and the agent
broke it while *recovering*.** It self-reported, unprompted, which is the behaviour to keep.

**So brief the RECOVERY, not just the prohibition:** if your commit goes wrong, the fix is
`git restore --staged` on *your own paths only*, or nothing at all — never a bare `reset`,
`checkout .`, or `add -A`. An agent told only what not to do will improvise something worse
under pressure.

**Caveat on the structural fix, learned the same day:** worktree isolation is right for
Python/native fan-outs, but a fresh worktree has no `node_modules` (it is gitignored), so a
JS/TS agent there cannot run its test suite without a multi-minute install first. For
frontend fan-outs the shared tree is the pragmatic choice — pay for verification of every
commit's contents instead, and expect attribution to be split across commits. Content survived
every one of the nine occurrences; authorship did not.
