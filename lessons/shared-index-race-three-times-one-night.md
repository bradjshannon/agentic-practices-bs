# Parallel agents on one working tree race the shared git index

**Symptom (2026-07-27, iotta conductor, three occurrences in one night):** an agent's
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
