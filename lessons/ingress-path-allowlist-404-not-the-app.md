# A new endpoint 404s for the device and 400s for you: the ingress has a path allowlist

**Symptom.** A device uploads to a newly-added endpoint and gets `404`. You test the same
endpoint from the host and get `400` — the app is clearly there and parsing your body. The two
observations contradict each other, so you start looking for a routing bug, a stale container, a
second instance, a deploy that didn't take.

**What actually happened.** The device does not reach the app the way you do. It goes through an
ingress — here a Tailscale Funnel — configured with an **explicit list of proxied paths**:

```
https://host (Funnel on)
|-- /tool        proxy http://127.0.0.1:8000/tool
|-- /telemetry   proxy http://127.0.0.1:8000/telemetry
|-- /device-logs proxy http://127.0.0.1:8000/device-logs
...
```

The new path was never added, so the *ingress* returned 404 and the request never reached the
application at all. Every localhost probe was true and irrelevant.

**The check that settles it in one command.** Test the new path AND a known-working sibling path
**over the device's actual route**, in the same breath:

```
POST https://host/uart-tap      -> 404
POST https://host/device-events -> 400   <- positive control: same route, reaches the app
```

The control is what makes it unambiguous. Without it, a bare 404 is consistent with "app is
down", "wrong host", "path typo", and "ingress doesn't know this path" — with it, only the last
one survives.

**Two traps in the fix itself.**

- On Tailscale, `tailscale serve --set-path <p> <target>` **silently downgrades that port from
  Funnel (public) to tailnet-only**. It prints `Removing Funnel for host:443` in its own output.
  A device reaching you from outside the tailnet drops off the instant you "just add a path".
  Use `tailscale funnel --bg --set-path ...` to add a path *and* keep it public.
- Do **not** reach for the blunt fix (`tailscale funnel --bg 8000`). That replaces the path
  allowlist with a catch-all and publishes everything the app serves — including admin surfaces
  that were deliberately excluded. **The allowlist is a security boundary, not configuration
  clutter.**

**The rule.** When a request fails for a device but succeeds for you, **you have not reproduced
the failure — you have tested a different system.** Re-run the probe over the subject's own
network path, with a known-good sibling request as a positive control, before forming any
hypothesis about the application.

**Why it generalises.** Any deployment with an ingress, reverse proxy, API gateway, service mesh
or firewall between clients and the app has a layer that can answer on the app's behalf. New
routes are added in the app's code and not in that layer, and the resulting 404 is
indistinguishable from a missing handler. The general form: **a probe that does not traverse the
same intermediaries as the real client is not a test of the same system**, and the more layers
exist, the more confidently a localhost check will mislead you.
