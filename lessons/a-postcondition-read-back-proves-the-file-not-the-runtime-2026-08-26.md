# A postcondition read-back proves the file, not the runtime

**Symptom:** Edited a JSON config field, read it back, saw the new value, reported "postcondition
passed." The runtime that reads that file never granted anything — it silently rejected the value
and kept behaving as if nothing changed.

**What actually happened:** A live server's authority for a device was governed by a config field
restricted to a small enum of valid strings. An edit set the field to a plausible-looking value
that was NOT a member of that enum. `json.load()` → `json.dump()` → re-read the file → the new
value was right there. Every mechanical check available at the file-edit layer passed. But the
consuming code looked the value up in a fixed policy table, found nothing, raised, and the caller
converted that into "deny" — which happened to look identical, from outside, to "the old, safe
default is still in effect." The bug was caught only by reading the RUNTIME's own live log output
for a fresh request after the edit and noticing the denial reason named the exact failure mode
("unknown stage"), not by anything the file-edit step could have told you.

**The rule:** A file-level postcondition (read the bytes back, assert the field equals what you
wrote) proves the WRITE succeeded. It does not prove the READER accepts the value as meaningful.
Whenever a config value is consumed against a schema, an enum, or any validation the writer
doesn't itself enforce, the real postcondition is downstream: exercise the actual runtime path
that reads the file (a fresh request, a fresh session, a fresh process — whatever "fresh" means for
that consumer) and read back a runtime-level signal that only appears when the value was accepted
as intended, not just present. Two different checks; passing the first is not evidence for the
second, and a bug that fails this way is invisible to the first check by construction — the file
looks perfectly correct.

**Why it generalises:** Any system where a human- or agent-editable config file feeds a stricter
internal enum/schema than the file format itself enforces has this exact trap: JSON has no enum
type, YAML has no enum type, most `.env`/`.ini`/`.toml` formats have no enum type. The write layer
is almost always more permissive than the read layer. Before trusting a config edit as "done,"
name what the CONSUMER does with an unrecognized value (raise? default? silently no-op?) and check
for that behavior specifically — don't stop at "the file now says what I wrote."
