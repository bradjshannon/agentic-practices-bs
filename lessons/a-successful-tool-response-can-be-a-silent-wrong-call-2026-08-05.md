# A successful tool response can be a silent wrong call

**Symptom:** Called an admin device-tool HTTP endpoint with `{"args":{"pct":50}}`. Got back
`200 OK`, `is_error: false`, `"ok: brightness 60%"` — a well-formed, non-error response. Only
noticed something was wrong because 60 didn't match the 50 that had been requested.

**What actually happened:** The endpoint's body schema used the key `"arguments"`, not `"args"`.
The mis-keyed request meant the server-side handler received no recognized argument, and the
device firmware's tool implementation had a documented fallback: no argument found → treat as a
read-only query → return the current value. The current value happened to be 60% (a leftover
from an earlier test), so the response looked exactly like a normal, successful set to a
plausible-but-wrong number.

**The rule:** A wrong parameter name does not have to produce an error. If the target has any
kind of "read current value" fallback path, a malformed write silently becomes a read, and the
read's result can look identical in shape to a write's confirmation — same 200, same `is_error:
false`, same "ok:" prefix. The only thing that gave it away was that the returned number didn't
match what was asked for, and that comparison is not automatic — nothing forces you to make it.

**Why it generalises:** Any API with a "call with `{}`/no args = read the current value"
convention has this failure mode built in. It's a common, reasonable design (this project's own
firmware documents doing exactly this on purpose, for tools that otherwise couldn't be read back).
The fix is procedural, not architectural: after any write call whose response includes the value
you just set, actively diff the returned value against what you sent, every time — don't just
check the HTTP status or the `is_error` flag. A second, explicit read-back call (with empty
args, forcing the read path) is the cheap way to get independent confirmation rather than trusting
the write call's own echo.
