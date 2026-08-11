# A running process masks a live-tree break until something restarts it

**2026-08-11. Measured window: 3 min 15 s.** An agent ran `git merge --no-commit` on a shared kernel
module (`conductorkit/core.py`) consumed by a second repo **through a live tree** — no package
boundary, no version pin, the file on disk is what the consumer imports. Two of the three conflict
markers landed in *code* rather than inside docstrings, so the module stopped parsing.

The specific trap is `--no-commit`: **it leaves the consumer broken for the entire resolution
window, which is however long thinking takes.** The right shape is to resolve in a scratch worktree
and land the result as one atomic write.

Measured from the consumer at that moment:

    python -m pytest tools/ -q
    -> Interrupted: 10 errors during collection
    E  SyntaxError: unmatched '}'   (line 946 of the OTHER repo's core.py)

Ten test files could not be collected. Five production modules import that kernel, including the
status-page generator.

**And the board still rendered.** `page-render-check.py` exit 0, masthead and threads panel present,
2.5 MB of correct output. The running server already had the module imported in memory, so it was
completely unaffected — and would have stayed unaffected until the next restart, deploy, or cold
generation, at which point it fails for every request.

## Why this is worth its own lesson

The estate had already had this outage: 90 minutes of `GENERATOR FAILED` + an ImportError traceback
served to every request, unnoticed, because **a page that responds does not look like a page that is
down**. The lesson drawn then was "check that it RENDERED, not that it loaded".

This instance adds the half that check cannot see. The render probe was **green throughout the
break**, correctly — the page really was rendering. The failure was latent, armed, and invisible to
the exact instrument built to catch its predecessor. A probe that reads the running process cannot
detect a break in the source that process was loaded from.

## The general form

> **A long-lived process is a cache of your source. Any check that goes through it measures the
> cache, not the source.**

This applies well beyond Python imports: a loaded config, a compiled template, an open database
handle, a JIT-warmed module, a container running an image whose source tree has since changed
underneath a bind mount.

## What to do

- **When two repos share code through a live tree, the consumer's suite is part of the producer's
  acceptance.** "My repo's tests pass" is not a result if the thing importing you cannot start.
  Brief it that way explicitly: producer-green + consumer-cannot-import is the precise shape of the
  original outage.
- **Add a cold check beside the warm one.** The render probe answers "is it serving?"; you also need
  "would a fresh process come up?" — a bare import, or a generation into a scratch path. They fail
  independently and only the second sees this class. Here that is literally
  `python -c "import conductorkit.core"` against the live tree: milliseconds, and nothing runs it.
- **Resolve conflicts in a scratch worktree, not in the tree the consumer reads.** `--no-commit`
  merges publish every intermediate state you pass through.
- **Treat a half-resolved conflict in shared source as an outage in progress**, not as ordinary
  work-in-progress. The window is not "until I finish"; it is "until something restarts", which is
  not under the author's control.
- **Do not fix it from outside.** The agent owning the merge should finish or revert to a valid
  state. A concurrent repair of a file someone is mid-merge on is how you get the tangle *and* the
  outage.

## The tell

You changed nothing in repo A, and repo A's suite stopped collecting. Read the traceback's file
path before assuming a regression: it may name repo B.

Related: `single-authority-not-mirrored-copies-2026-08-01.md`,
`a-service-that-cannot-import-its-own-code-still-returns-200-2026-08-05.md`.
