# Shared state and concurrent agents

## "Clean" does not mean "current"

*2026-07-21*

**Symptom.** An agent searched a repository working copy for a module that a recent change had
added. `find` did not locate the file. Listing tracked files did not show it. Grepping for the
import that referenced it found nothing. Three independent checks agreed the module did not
exist — so the agent began reasoning about a change that had "added an import without adding the
file."

The file existed. It was in the branch's tip on the remote, and had been for hours.

**What actually happened.** The working copy was a **shared checkout** used by several
concurrent agent sessions. It sat on the right *branch name* but several commits behind the
remote tip, with a **completely clean status** — no uncommitted changes, nothing to warn anyone.
A preflight check had reported it as "clean," which the agent read as "current." Those are
different properties, and only one of them was checked.

**The rule.**

- Before concluding a file, symbol, or line **does not exist**, confirm you are reading a
  current tree: fetch, then read from the **remote ref** (`show <remote>/<branch>:<path>`), or
  create a worktree from the remote ref.
- **"Clean" answers "are there uncommitted changes." It says nothing about how stale you are.**
  Treat them as separate checks.
- A negative result from a working copy of unknown freshness is not evidence of absence.

**Why it generalises.** Any shared or long-lived checkout drifts. The failure is quiet by
construction — every tool reports success, and the absence looks like a real finding.

---

## Assume you are not the only agent in the repository

*2026-07-21*

**Symptom.** An agent wrote several files into what it believed was its own working copy. The
files landed on an unrelated branch belonging to a different concurrent session, mixed in with
that session's uncommitted work.

**What actually happened.** Multiple agent sessions shared one machine and, in some cases, one
checkout. The main checkout was routinely on whatever branch another session was using — and it
changed under the agent mid-run, without any signal.

**The rule.**

- **Give each session its own worktree**, and never write to the shared main checkout. Read from
  it freely; write only to a worktree you created.
- **Pass the repository path explicitly to every command** (`git -C <path> …`) rather than
  relying on the shell's working directory. A directory-changing command that later reports on
  the wrong repository is authoritative-sounding and wrong — a particularly bad combination.
- Re-check assumptions about branch and HEAD **at the moment you use them**, not once at start.
  In a shared checkout, that state is another process's variable.
- Clean up worktrees you create, and only after confirming the work is pushed.

**Why it generalises.** Parallel agents against one repository is now the default, not the
exception, and git's ergonomics assume a single human operator with one working copy in mind.
Nothing in the tooling will warn you that the branch moved.
