# `git worktree remove` can drop the registration while leaving the directory locked — don't force past it

**Symptom.** Cleaning up stale, merged, clean git worktrees (the exact test a prior session
validated: `HEAD` merged into `origin/main`/`origin/test` AND `git status --porcelain` empty).
`git worktree remove <path>` failed with `Permission denied` on all 5 candidates. A follow-up
plain `rm -rf <path>` on the same directories failed differently: `Device or resource busy`.

**What actually happened.** `git worktree remove` had already dropped the registration from
`.git/worktrees/` — `git worktree list` no longer showed any of the 5 directories — despite the
directory-deletion step failing. So git was left in a *consistent but incomplete* state: the
worktree is unregistered (the state that matters for git's own bookkeeping and for a future
`git worktree add` at the same path) but the physical directory remains on disk. Nothing was
corrupted; nothing needed repair. Did not investigate further whether a live process had a file
handle open in one of the directories (checked running processes' command lines for a literal
path match — found none, which only rules out the path appearing in `CommandLine`, not e.g. an
open handle from a process whose `cwd` was set there without it showing in the command line).

**The rule.** `git worktree remove` can partially succeed — registration gone, directory still
locked — and that partial state is safe to leave alone. Do not escalate to `--force`, do not try
to hunt down and kill whatever holds the directory, and do not retry a plain `rm -rf` more than
once. "Merged and clean" is necessary but not sufficient for a *fully clean* removal on a host
where something else may have a handle open — it does not prove the directory is free to delete
right now. Treat `Permission denied` / `Device or resource busy` on a worktree removal the same
way you'd treat a live process holding a file open: a signal to back off, not an obstacle to route
around. The git-side hygiene goal (no stale registrations) is achieved either way; a few orphaned
directories are disk clutter, not a correctness problem, and will usually clear themselves once
whatever holds them exits.

**Why it generalizes.** Any agent running git-worktree cleanup on a multi-session host (several
agents, or several editor/IDE windows, sharing one checkout's worktrees) can hit this. The
generalizable move is: verify with `git worktree list` that the registration is actually gone
after a failed `remove` (it may be, even though the command reported failure) before assuming the
whole operation failed and trying something more aggressive.
