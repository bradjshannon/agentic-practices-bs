# A recovery check placed after the failure it recovers from never runs

**2026-08-12. Measured outage: ~4h 55m**, from ~19:37Z to 00:32Z. A status board served
`GENERATOR FAILED` plus an ImportError traceback to every request. Nobody was looking, because the
run that broke it had already ended.

The server publishes by **re-executing its generator from HEAD on every new commit** — commit-to-
publish, deliberately, so editing the working tree cannot break the live page. That mechanism works.
What it does not cover is everything the generator *imports*: those are ordinary modules, cached in
`sys.modules` for the life of the process. When a new symbol arrived in one of them from another
workstation, the freshly published generator imported a name the running process had never heard of.

    ImportError: cannot import name '_find_file_html' from 'conductor_render_core'
      raised at conductor-status.py:309

The same tree, generated from the CLI seconds later, produced 2.1 MB of correct page. **The code was
fine. Only the live process was wrong.**

## The part worth a lesson

The server already had the right mechanism. It watched its own source at HEAD and restarted itself
when that changed — precisely so a published page could never outrun the process serving it. It was
placed like this:

```python
if sha != _gen_sha:
    gen = _load_generator()      # <- raises
    _gen_sha = sha
    if _self_source_changed():   # <- never reached
        _request_restart()
```

`_load_generator()` raised, so `_gen_sha` was never advanced, so **every subsequent request took the
same branch, raised in the same place, and never reached the restart either.** The one mechanism
that could have brought the process back to life was unreachable in exactly the state it existed
for. It was not missing, not disabled, not wrong — it was **downstream of the thing it recovers
from**.

That turned a self-healing system into one that needed a human. Recovery required stopping the
process, and an agent had been told (by the diagnostic tool's own text, wrongly) that it could not
do that. So the board sat dead until someone read the room.

## The general form

> **Put a recovery path BEFORE the operation it recovers from, never after.** Anything sequenced
> after a failure is conditional on that failure not happening — which is the one case it is for.

The same shape, wearing other clothes:

- A retry that lives inside the `try` block it is meant to retry.
- Cleanup after the call that leaks, rather than in `finally`.
- A health check that runs after the initialization it is supposed to catch failing.
- A circuit breaker whose counter increments after the call returns.
- An alert emitted on the line following the crash.

Each looks correct while reading top to bottom, because the recovery is *textually adjacent* to the
failure. Adjacency is not reachability.

## The tell

Ask, for every guard you write: **what is the state of the world in which this guard is most
needed, and does control actually reach it in that state?** If the answer requires the preceding
line to have succeeded, the guard is decoration.

The cheap test is a unit test that makes the preceding operation raise and then asserts the guard
still fired. It is three lines and it would have caught this before it shipped.

## The second, smaller lesson

Hot-reload that reaches only the entry point is not hot-reload. If a module is re-executed from a
published source but its imports are resolved normally, **the reload boundary is one file deep** and
everything behind it is frozen at process start. Either watch the whole imported surface, or accept
that a restart is the publish mechanism and make the restart reachable.

Deriving the watched set from the entry module's own imports — rather than hand-listing it — is what
keeps that from decaying the next time someone adds an import.

## Bonus: the diagnostic tool lied about who could fix it

The probe that correctly detected the dead board printed a recovery procedure labelled
**OPERATOR ONLY**, on the stated grounds that an agent's process-stop call is refused. It is not
refused. The three documented steps ran fine and the board came back the same minute — after that
text had already sent one agent looking for a human.

> **A recovery path that claims to be unavailable is as expensive as one that does not exist.**
> Wrong "you can't do this" text costs the entire outage, not a round-trip. Measure the claim before
> writing it, and re-measure it when acting on it.

Related: `a-running-process-masks-a-live-tree-break-until-it-restarts-2026-08-11.md`,
`a-service-that-cannot-import-its-own-code-still-returns-200-2026-08-05.md`,
`a-check-that-cannot-fail-reports-holds-forever-2026-08-01.md`.
