# Commit to a shared branch without touching your own checkout

**Class:** write path. Replaces a normal `git add`/`commit`/`push` when the writer's own working
tree, index, or checked-out branch must stay untouched.

## The problem it fixes

Many agents share one physical host, each in its own worktree, often mid-way through unrelated
uncommitted work on a feature branch. A background utility that needs to append one row to a
shared log — a collab log, an audit trail, a counter — cannot afford the normal write path:
`git checkout <target-branch>` would blow away the caller's own uncommitted changes, and even a
same-branch `git add`/`commit` risks committing whatever else happens to be staged.

Concretely: a collab-log CLI called from dozens of independent worktrees, all logging onto one
canonical timeline (`origin/main`), regardless of which feature branch each caller happens to be
on. The write has to be `origin/main`-scoped, atomic per call, retryable under a concurrent-writer
race, and **structurally incapable** of touching the caller's HEAD, index, or working files.

## The mechanism

Git's plumbing commands operate on refs and objects, not on a checkout. Building a commit this way
never reads or writes the caller's real index or working tree at all:

```python
def append(base_sha, new_content, path, message):
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(td) / "index")}
        run(["read-tree", base_sha], env=env)
        blob = run(["hash-object", "-w", "--stdin"], input=new_content, env=env)
        run(["update-index", "--add", "--cacheinfo", "100644", blob, path], env=env)
        tree = run(["write-tree"], env=env)
        return run(["commit-tree", tree, "-p", base_sha, "-m", message], env=env)
```

Then `git push origin <that-sha>:main` — never `git push origin HEAD:main`, which would push
whatever the caller's actual branch tip is. The caller's own `git status`, current branch, and any
uncommitted files are provably unaffected, because nothing above ever reads `.git/HEAD` or the
real `.git/index`.

**On a push rejection (a concurrent writer landed first), retry the whole loop from a fresh
`fetch`** — recompute anything derived from prior state (an auto-incrementing id, a "next line
number") on each attempt, not once up front, or a retry silently reuses a value the winner already
claimed.

## What it does not replace

This is for one-file, single-writer-per-attempt appends onto a ref nobody else is actively
rebasing. It is not a substitute for normal commits when the caller *wants* the change on their
own branch, and it is not a merge strategy — two writers racing this loop each fully succeed (both
commits land, in whichever order won), they do not need to resolve a content conflict, because
each attempt starts from a fresh base and only ever adds its own line.

## Verify it, don't just build it

The property worth testing directly, not assuming: after a call, the caller's checked-out branch
name is unchanged, `git status --porcelain` shows nothing new, and the file at the ref used never
appears in the caller's own working tree. A test that only checks "did the remote get the commit"
can pass while the mechanism silently also mutated the caller — assert the negative explicitly.
