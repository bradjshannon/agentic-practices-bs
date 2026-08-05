# A service that cannot import its own code still returns HTTP 200

**2026-08-05, server conductor.** A live status page — the human's actual channel for reading
and replying to a running agent — had been silently down for ~26 hours. Every request to it
returned `HTTP 200`.

## What happened

A refactor moved ~1,700 lines of shared logic out of a page-generator script into a new module,
`conductorkit.core`, imported from a sibling repo clone by path (`sys.path.insert` +
`import conductorkit.core`). The sibling repo was never created or pushed — no local clone, no
remote under any account. Every subsequent render hit `ModuleNotFoundError` inside the page
generator, which the serving wrapper caught and turned into a small HTML page: `<title>status:
render failed</title>`, `<p>ModuleNotFoundError: check the server log.</p>` — served with a
`200` status code, because the *HTTP handler* succeeded even though the *page* it was asked to
build did not exist.

The human read the page as "quiet," not "broken," for over a day. `curl -o /dev/null -w
'%{http_code}'` — the fastest possible health check — would have reported the service healthy
the entire time.

## The general shape

This is the same failure family as a liveness endpoint that answers `{"status": "ok"}` without
checking whether the thing behind it actually works: **the transport layer succeeding is not the
same claim as the payload being real.** An error-handling wrapper that turns an exception into a
well-formed HTTP response is doing its job at its own layer (don't crash the process, give the
client *something*) — but if nothing downstream distinguishes "here is your data" from "here is
an apology for missing data," both look identical to any check that only reads the status code.

The refactor itself compounds the risk: a change that deletes ~1,700 lines and replaces them with
an import from a repo that doesn't exist yet is a two-commit change (add the dependency, THEN
depend on it) that landed as one. Nothing in the commit, the CI (there wasn't one covering this
path), or a status-code check could have caught the gap between them.

## The rule

**A health check that only reads the transport status code cannot tell "served" from "served an
error page."** If a page/response can legitimately render an error state with a `200`, the check
must read the body — a title string, a content-length floor, a marker only the real payload
contains — not just the connection outcome. And a refactor that introduces a new hard dependency
on an as-yet-unpublished sibling artifact should ship the artifact first, in its own commit,
verified reachable, before anything is repointed at it.
