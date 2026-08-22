# A scoped `git add <path>` + `git commit` can still sweep up a shared checkout's leftover mess

**Symptom:** ran `git add conductors/server/needs-you.md` (one specific file) followed by
`git commit -m "..."` with no `-a` and no other pathspec, expecting a single-file commit. The
resulting commit touched 7 files — the one intended, plus 6 files belonging to a completely
different, actively-running process (another domain's conductor, concurrently rewriting its own
status files in the same shared git checkout).

**What actually happened:** earlier in the same session, a failed recovery sequence left the
index in an unexpected state. The chain was: `git rebase` refused to start because the working
tree had unrelated dirty files (another process's live writes) → tried `git stash push -- <path>`
on just those files, which kept re-dirtying due to a live process racing the stash (not a caching
bug — the other process was genuinely rewriting the file faster than it could be parked) →
switched to a `git cherry-pick <sha> --strategy-option=ours`, run while still on the shared
branch (not a detached/temp ref) → the cherry-pick hit conflicts, auto-resolved them via the
`ours` strategy option, and staged that resolution → `git cherry-pick --abort` was run, which
correctly aborted the cherry-pick *operation* but did not fully clear everything the conflict
resolution had touched in the index. The dirty files were sitting there, unstaged, both before
and after — `git status` looked identical at every checkpoint — so nothing about the visible
state signaled that the index still carried the abort's residue. The next `git add <one-file>` +
`git commit` picked up that residue along with the intended file, because `git commit` without a
pathspec commits **the whole index**, not just what the most recent `add` touched.

**The rule:** in a shared checkout with concurrent writers, after ANY conflict-resolution
operation (a cherry-pick, a merge, a rebase — anything that can auto-resolve and stage), run
`git status` **and** inspect the index directly (`git diff --cached --stat`) before trusting that
the next scoped `git add` + `git commit` is actually scoped. `git status` showing the *working
tree* as clean or predictably-dirty is not proof the *index* matches your mental model — the two
can diverge silently, and a scoped `add` only adds to whatever the index already contains; it
never resets it. Cheaper insurance: verify every commit's actual contents with `git show --stat
HEAD` immediately after committing, before pushing — this is what caught the mistake here, in
time, because the bad commit had not yet reached `origin`.

**Recovery, for the same situation:** if the bad commit is still local-only (check `git log
--oneline HEAD` vs `origin/<branch>` before assuming), `git reset --mixed <last-good-sha>` undoes
the commit and unstages everything without touching the working tree — critical when the working
tree holds another process's live, uncommitted writes that a `--hard` reset would silently
overwrite. Redo the real change in an isolated `git worktree` (a fresh checkout off the remote
branch, physically separate from the shared tree) so the commit can only ever contain what you
explicitly wrote there, then push from that worktree and remove it.

**Why it generalises:** any agent working in a checkout another agent/process also writes to —
not just this estate's IXP/conductor-bs shared clones — is exposed to the same failure whenever a
recovery sequence involves a conflict-capable git operation (rebase, merge, cherry-pick). The
specific trigger here (a live concurrent writer racing a stash) is estate-specific; the general
shape — "a scoped commit trusts the index, and a prior aborted operation can leave the index
lying to you" — is not. The mitigating pattern (isolated worktree for any commit in a shared,
concurrently-written checkout, plus a post-commit `--stat` check before every push) is directly
portable to any multi-agent setup sharing a git working directory.
