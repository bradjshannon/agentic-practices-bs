# A port you did not verify free answers with someone else's content — and the read looks fine

**2026-08-14.** Cost: a correct fix reported as failed, then a service taken down for ~10 minutes
while diagnosing the wrong thing.

## What happened

A fix changed a page generator. To verify it, the agent started a throwaway static server:

```
cd <scratchpad> && python -m http.server 8799
```

8799 was already held by the application's own status server. On Windows the second bind did not
fail loudly enough to notice, and **both processes were reachable on that port**. Requests were
answered by whichever, so:

- The browser loaded a page that looked right in structure and had the OLD behaviour.
- Every probe agreed with every other probe, because they were all reading the same wrong source.
- The agent concluded the fix had not taken, and started looking for a second bug that did not exist.

The fix had been correct the whole time.

Worse, the collision was invisible until the *other* process died. When the status server was
restarted (for unrelated reasons), the throwaway server inherited the port and began serving a
**directory listing** to the operator's real URL through a reverse proxy.

## Why the usual instincts do not catch it

Every check the agent reached for was downstream of the lie:

- *Reload the page.* Same port, same wrong answer.
- *Add a cache-buster.* Confirms it is not cache; it is not.
- *Read `document.title` and the DOM.* All internally consistent, all from the wrong source.
- *Grep the file on disk.* The file was correct. That is what made the disagreement so confusing.

The tell that worked, and it is cheap: **compare what the server returns against the bytes on disk.**

```
curl -s "http://127.0.0.1:<port>/<file>" -o /tmp/served
wc -c /tmp/served <the file on disk>
```

`2355659` vs `2362393` ended the investigation in one command. Content identity, not content
plausibility, is the discriminator — a stale copy of a big generated artifact looks entirely
credible on inspection.

## The rule

**Before binding a port for a throwaway server, establish that nothing else owns it — and after
binding, prove the server you started is the one answering.**

- Prefer a port nobody could plausibly be using, and still check.
- `Get-NetTCPConnection -LocalPort <p> -State Listen` / `ss -ltnp` before you start, and read the
  owning process, not just whether something is there.
- After starting, fetch one file and compare its **size or hash** to the file on disk. If they
  differ, you are talking to someone else.
- Kill what you started, explicitly, when you are done. A throwaway server that outlives its purpose
  is waiting to inherit a port from a process that dies later — which is exactly how a debugging aid
  became an outage.

## The generalisation

This is the shared-mutable-resource failure wearing network clothes. A port is a global namespace
with no ownership check at bind time, so "I started a server, therefore I am talking to my server"
is an assumption, not an observation — the same class as assuming a shared git index, a fixed
temp path, or a shared scratchpad directory belongs to you because you wrote to it.

**Any time a probe and the artifact on disk disagree, suspect that they are not the same artifact
before you suspect the change.**

Related: [`measure-the-instrument-before-the-effect`](measure-the-instrument-before-the-effect.md),
[`shared-state`](shared-state.md),
[`a-service-that-cannot-import-its-own-code-still-returns-200-2026-08-05`](a-service-that-cannot-import-its-own-code-still-returns-200-2026-08-05.md).
