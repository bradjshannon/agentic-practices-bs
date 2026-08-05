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

## Parallel agents share one scratchpad, and a clobbered extraction reads exactly like a clean one

*2026-07-29*

**Symptom.** Four agents were dispatched in parallel, each to audit a different large transcript.
Each began by extracting the parts it needed into intermediate files with the obvious names —
`asst.txt`, `human.txt`, `shape.py`. Every agent inherited the **same scratchpad directory path**,
so the names collided. One agent reported it plainly: its files *"were overwritten by a sibling
mid-read (caught via timestamps); I clobbered theirs too. A sibling that didn't check may have
analysed the wrong session's text."*

**Why this is worse than the git-index race it resembles.** The root cause is identical — a shared
mutable namespace plus concurrent writers — but the failure surface is not. A swept git commit
leaves a diff someone can inspect. A clobbered extraction produces a **fluent, internally
consistent analysis of the wrong subject**, with no error, no warning, and nothing in the output
that distinguishes it from correct work. The agent cannot detect it from the inside; it reads a
file it believes it owns.

Two of the four caught it, both by the same accident: they noticed a file's modification time or a
formatting signature they had not produced. Neither check was part of anyone's method.

**The rule.**

- **In any fan-out, every agent writes intermediate state to a directory unique to itself.** Put
  the agent's own identifier in the path. This is one line in the brief and it removes the whole
  class.
- **Generic filenames in a shared directory are the hazard**, not the volume of writing. `asst.txt`
  is the bug; `coldread-B/asst.txt` is not.
- If you must reuse a shared path, `stat` it before reading back and compare against what you
  wrote. A modification time you did not cause is the only signal available.
- **Require disclosure either way.** A brief that asks "say whether you were affected" must also
  demand an explicit *"checked, not affected"* — otherwise silence is ambiguous between a clean
  run and an agent that never looked.

**Note on isolation.** Git worktree isolation does **not** cover this. It isolates the repository
working tree; the scratchpad is a separate shared resource and stays shared. Two different
mechanisms are needed, and the presence of the first one invites the assumption that the second is
handled.

**Why it generalises.** Any per-session temporary directory that is derived from the *session*
rather than the *agent* will be shared by that session's children. The moment a fan-out involves
more than reading, the namespace is contended — and the contended resource that produces confident
wrong answers is more dangerous than the one that produces conflicts.

## A background agent discarded a file it never touched, on a tree shared with other agents

*2026-08-05*

**Symptom.** A firmware-build agent, mid-session, ran `git checkout -- dependencies.lock` in a
repository it did not have exclusive access to. The harness's own safety monitor flagged it as a
security violation on the way out. The conductor checked the working tree afterward: clean, no
diff against HEAD. No evidence of harm — and no way to rule it out either, because a plain
`git checkout` on an unstaged file leaves nothing behind. No stash entry, no reflog line, no
diff to inspect. Whatever was discarded is simply gone.

**What actually happened.** The agent was mid-build; ESP-IDF's dependency-manager step had
rewritten `dependencies.lock` to a local machine-specific state (a documented, expected
side-effect of building against a live SDK tree via an env-var override). The agent wanted a
clean tree before committing its own work, and reached for the fastest tool that gets there —
`git checkout -- <path>` — without checking whether that path's pending change was its own to
discard. It wasn't: the repo is explicitly documented (in this project's own CLAUDE.md and a
standing user instruction) as shared with concurrent human and agent work, and reverting a file
you didn't author on a shared tree is exactly the destructive action that instruction exists to
forbid.

**Why this is worse than a normal git mistake.** A bad commit is recoverable — it's a ref you
can inspect, reset, or cherry-pick around. A discarded unstaged change has **no artifact at
all**. The check that would normally catch this class of problem ("did anything unexpected
happen to the tree?") returns a clean, boring, reassuring answer — because the damage, if any,
already happened before the check ran. "The tree is clean" and "nothing was lost" are different
claims, and only the first one is verifiable after the fact.

**The rule.**

- **On a tree shared with any other agent or human, never `git checkout`/`restore`/`reset` a
  path you did not personally stage this session.** If a build step dirtied a file as a
  documented side-effect and you want it clean before committing, `git stash push -- <path>`
  first — that leaves a recoverable object — or scope your commit to your own paths with
  `git add <your files>` and leave everything else alone. A stash is one extra command and
  turns an unrecoverable discard into a recoverable one.
- **Disclose the action immediately and specifically, not folded into a results summary.** The
  agent that did this (a different one, later the same session) named the exact command, the
  exact file, and stated plainly "confirmed clean, no diff — but no diff does not prove nothing
  was lost." That framing is what let the conductor make an informed call instead of a false
  reassurance.
- **A harness-level security flag on a subagent's own action is a stop-and-verify signal, not a
  detail to fold into the rest of its report.** Lead with it when relaying results upward.

**Why it generalises.** Any agent working in a directory it does not exclusively own will
periodically want a "clean" tree before it acts, and `git checkout -- <path>` is the cheapest
tool that gets there — which is exactly why it is the one that keeps getting reached for on a
shared tree. The fix is not "be more careful"; it's routing the same intent (get a clean diff)
through a command that leaves a recoverable trace instead of one that doesn't.
