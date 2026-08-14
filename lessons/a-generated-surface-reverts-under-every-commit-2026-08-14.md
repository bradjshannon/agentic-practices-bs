# A live data file in a git working tree is reverted by every commit's pre-commit stash

**Symptom.** An operator's message, typed into a web UI and submitted, never arrived. He also
reported the thread it belonged to as "gone" from the page. Both the thread and the store were
intact when checked minutes later, and nothing had errored.

**What actually happened.** `pre-commit` stashes **all unstaged changes** before running hooks and
restores them afterwards, regardless of what was staged. The status page's stores — append-only
JSONL written by the server on submit and read at render time — live inside the same git working
tree and are essentially always dirty. During each stash window the on-disk file is HEAD's version.
A render in that window shows a thread missing its recent rows; a server append in that window is
destroyed by the restore. Four commits landed inside four minutes, and the message went into one of
the gaps.

**The rule.** A file that a live process writes must not sit in a working tree that something else
runs `git` against. If it must, the writer and the committer have to be serialised, or the file has
to be excluded from whatever the commit tooling stashes. Do not reason about the window as small:
the failure is silent on both sides, so its rate is invisible and only the operator notices.

**Why it generalises.** The stash is invisible in the normal reading of "commit" — it is a
correctness mechanism for hooks (so hooks see exactly what is staged), and it is doing its job
correctly. The hazard comes from a **category error about the directory**: a git working tree is
treated as a place files live, when for the duration of a commit it is a place files are
temporarily *replaced*. Anything that reads or writes a path in that tree from outside git's
process is racing a rollback it cannot see.

The general test: **for every file a service reads or writes, ask what else takes a write lock or a
temporary rollback on that path.** Backup tools, sync daemons, editors with atomic-save, and
version control all do this, all briefly, all silently. The service's own code is correct
throughout; that is what makes it hard to find from the service's side.
