# A pre-commit hook subprocess inherits GIT_DIR/GIT_WORK_TREE from the committing repo — `git -C <other-repo>` silently reads the wrong tree

## Symptom

A commit in a worktree (branch `lot/cpub-kit-inc5-bs`) was blocked for ~4 hours by a pre-commit
hook (`conductorkit-freshness`) reporting: *"conductor-pub branch 'lot/cpub-kit-inc5-bs' has no
upstream configured."* But `lot/cpub-kit-inc5-bs` was never a branch of `conductor-pub` — it was
the *committing* repo's own branch name. Manually re-verifying the actual `conductor-pub` clone
showed it cleanly on `dev`, tracking `origin/dev`, with no uncommitted changes. Retried the commit
three times; identical failure every time, always naming the wrong repo's branch under the right
repo's path.

## What actually happened

The hook's `_git()` helper called `subprocess.run(["git", "-C", str(pub), *args], ...)` with no
explicit `env=`, so it inherited the parent process's environment. **Git sets `GIT_DIR` and
`GIT_WORK_TREE` for every pre-commit hook subprocess it spawns, pointed at the repo actually being
committed to.** Git honors those env vars over an explicit `-C <path>` when both are present — so
every `git -C <pub> ...` call in the hook silently operated on the *committing* repo instead of the
resolved `pub` clone, while the hook's own error-message string interpolation used the `pub`
variable (which held the *correct* path, from a separate, working resolver call) — so the printed
error named the right repo and the wrong branch, which reads exactly like real staleness.

Confirmed by direct reproduction: `GIT_DIR=<other-repo>/.git GIT_WORK_TREE=<other-repo> git -C
<target-repo> rev-parse --abbrev-ref HEAD` returns the *other* repo's branch, not the target's.

## The rule

**Any tool that does `git -C <resolved-path>` inside code that might run as a git hook must
explicitly scrub `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`/`GIT_OBJECT_DIRECTORY`/
`GIT_ALTERNATE_OBJECT_DIRECTORIES`/`GIT_COMMON_DIR` from the subprocess environment first** (pass
`env={k: v for k, v in os.environ.items() if k not in _GIT_ENV_VARS_TO_SCRUB}`), not just pass
`-C`. `-C` is a request; these env vars are binding when present, and git hook subprocesses always
carry them.

## Why it generalises

Any conductor/CI tool that resolves a *different* repo's path and then shells out to `git -C
<that path>` from *inside* a pre-commit hook (or any process git itself spawned) is at risk of this
exact failure — and the failure mode is specifically deceptive because the printed path is correct
even though the read is not. Nobody has audited this codebase for a second instance of the same
pattern; grep for `subprocess.run\(\["git", "-C"` across any tool invoked as (or downstream of) a
git hook.
