# A tolerant batch policy becomes a lying ack when you put a per-record protocol on top

**2026-07-31, iotta.** A streaming ingest endpoint answered `{"ok": true}` for records it had
silently thrown away.

## What happened

A drain-on-demand batch endpoint (`POST /uart-tap`) had a deliberate, documented, and *correct*
policy, stated in its own docstring:

> non-dict / malformed entries (including an entry with a missing/unrecognized `channel`) are
> **dropped rather than failing the whole batch**

For a batch upload that is the right call: one bad record should not cost you the other ninety-nine.
The function returns a summary and does not distinguish "stored 100" from "stored 99, binned 1".

Later, a near-realtime streaming channel (`WS /capture-stream`) was built to feed the *same* store,
this time with a **per-record acknowledgement** — explicitly so that "a rejected record is
distinguishable from an accepted one." The handler called the same store function and treated a
non-`None` return as success.

Measured against a live server with a real WebSocket client — two frames, identical except one omits
a required field:

```
WITH kind    ack -> {"ok": true, "type": "uart", "seq": 201}
WITHOUT kind ack -> {"ok": true, "type": "uart", "seq": 202}
ring count: 1
```

Earlier in the same session, 6 serial records and 4 audio chunks were all acked `ok: true` and the
ring held **zero**. The feature's headline promise — one merged time-ordered view of serial and
audio — rendered with no serial in it, and nothing anywhere reported an error.

The bitter part: this feature's own design doc cited the incident that motivated it — a client that
advanced its cursor past bytes the server had 404'd, discarding 125 bytes of capture. The streaming
path reproduced that exact disease one layer down, with a green ack on top.

## Why no test caught it

The suite was thorough and passed — including an end-to-end test through the real ASGI stack with
`TestClient.websocket_connect`, not a hand-rolled fake. It still missed this, for a reason worth
internalising:

**Every test constructed well-formed records, so the drop path was never executed.** The tests
covered the transport, the routing, the merge, and the annotation logic. The one line they never
reached was the one where a record vanishes.

A test suite is written from the same mental model as the code. If the author did not think "what
if the record is malformed *here*, where the contract is per-record rather than per-batch", neither
the code nor its tests will contain that case. This is why a *different instrument* — driving the
real process from outside, with deliberately wrong input — finds a different class of bug. It is
not redundancy with the unit suite. It is a different question.

## The general rule

**A policy is only correct relative to the protocol wrapped around it. Re-derive it at every layer
that reuses it — a tolerant policy inherited under a stricter contract becomes a lie.**

Concretely, when a lower layer is deliberately lenient:

- **An acknowledgement must mean *persisted*, not *the call returned*.** If the storage call cannot
  tell you which records it accepted, that is a missing return value, not an acceptable ambiguity —
  compare counts before/after, or change the signature.
- **Look for the seam whenever a store gains a second caller with different semantics.** Batch vs
  stream, bulk-import vs single-write, best-effort vs transactional. The lenient path is usually the
  older one and its leniency is usually documented and correct; that documentation is what makes the
  new caller trust it.
- **When you test the fix, require a positive control in the same breath** — assert that a
  well-formed record still acks `ok: true` and still persists. Otherwise "reject everything" passes.

## The tell

If you can describe a return value as "non-`None` means it worked", ask what it returns when it
partly worked. Silent partial success is the failure mode that survives every green suite, because
success is what it looks like from the inside.
