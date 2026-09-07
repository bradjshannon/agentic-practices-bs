# `worktree_fleet.py reap` never removes a live worktree, even when its branch is fully merged

**Symptom.** Asked to "clean up worktrees, space on C:\ is tight." `worktree_fleet.py reap --apply
--prune-branches` ran cleanly (no error, no block) but reported `SAFE-PRUNE worktrees (0)` for every
repo, even though a hand-built classification found 74 of 100 registered worktrees fully merged
into their default branch. Nothing was actually freed.

**What actually happened.** `worktree_fleet.py`'s SAFE-PRUNE classification for a worktree requires
the directory to already be **gone** (`dead_dir`) — its own source comment: "SAFE-PRUNE worktree
gone, or session directory gone, AND the branch is fully merged." A live, present worktree
directory is always classified `KEEP`, regardless of merge status — the tool's stated purpose is
preventing an unmerged branch from becoming *invisible* (a dangling registration losing real work),
not reclaiming disk space. Those are different problems that happen to share a CLI verb ("reap").

**The fix, this run.** The tool's own removal primitives (`unlink_all_junctions`, which unlinks a
`node_modules` junction before `git worktree remove` can follow it and recursively delete the
shared source) are safe and reusable. Wrote a ~40-line script that imports `worktree_fleet` as a
module, re-classifies every worktree with `is_merged()`, and for anything merged AND live calls the
same junction-unlink-then-`git worktree remove` sequence the tool itself uses for its own
SAFE-PRUNE case. Result: 65 of 68 candidates removed cleanly, 3 correctly refused by git itself
(genuinely dirty — uncommitted work sitting on top of a merged branch, which is exactly the case
`git worktree remove` without `--force` is supposed to catch). Then ran the *actual* `reap --apply
--prune-branches` per repo to clear 98 now-orphaned branch registrations, which IS what that verb is
for. Net C:\ free space: 5.4GB → 7.7GB.

**The rule.** Before assuming a tool's name matches your goal, read its own classification logic,
not just its CLI surface — `reap --apply` sounding like "clean things up" and `reap`'s own docstring
being explicit about "not disk space" are both true at once, and only one of them survives a
skim.

**Why it generalises.** Any tool built to solve problem A (invisible lost work) will accumulate
users who assume it also solves adjacent problem B (disk space) because the verb overlaps. The fix
generalizes too: a tool's own safety primitives (junction unlinking, merge-checking) are almost
always safely reusable for a narrower or wider version of the same job — reach for them via import
before hand-rolling the removal logic from scratch, which is where the real risk (recursing through
a junction) lives.

The workaround script now lives at `conductor-bs/tools/reap_merged_worktrees.py` (promoted from a
scratchpad one-off) — a genuine standing tool other conductors can reach for, not a script to
rebuild from this lesson each time it's needed.
