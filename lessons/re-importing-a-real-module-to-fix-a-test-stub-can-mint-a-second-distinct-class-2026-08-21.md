# Re-importing a real module to undo a test stub can mint a SECOND, distinct class object — 2026-08-21

## Symptom

A new test file constructed real `openai.RateLimitError`/`openai.InternalServerError`
instances and asserted that production code retried on them. Every retry test failed with
the production code's exception apparently un-recognized — `isinstance(exc,
retryable_tuple)` returned `False` for an exception that unmistakably *was* one of the
listed classes. Three separate "fixes" were applied in sequence, each addressing a real,
reproducible symptom, and each left the underlying bug in place:

1. Discovered another test file in the same suite unconditionally replaced
   `sys.modules['openai']` with a bare stub at its own collection time, poisoning every
   later-collected file. Fix: force a real re-import before running.
2. That re-import then broke on `ImportError: cannot import name 'URL' from 'httpx'` —
   the SAME other file had also stubbed `httpx`, and the real `openai` package needs a
   real `httpx` at import time. Fix: purge and re-import `httpx` too.
3. The retry tests were STILL failing, with the exact same symptom. Direct debugging
   (`isinstance(exc, mod.openai.RateLimitError)` checked in isolation) said `True`. The
   full suite said `False` for the identical-looking check.

## What actually happened

The re-import fix from step 1/2 was called **inside a helper invoked once per test**
(`_install_stub_modules()`, called by every test's setup). It purged and re-imported the
real `openai` package **unconditionally, every single call** — with no check for whether
the currently-cached module was already the genuine one. Since the fixture purge deleted
`sys.modules['openai']` and then did a fresh `import openai`, Python re-executed the
entire package's `__init__.py` from scratch each time, producing a **brand-new module
object with brand-new class objects** on every test. `openai.RateLimitError` from test 1's
import and `openai.RateLimitError` from test 5's import are two different Python objects
with the same qualified name — `isinstance()` checks identity through the class's `type`
object, and two separately-executed module bodies never produce `is`-identical classes.

The test file's own `import openai` at the top of the file bound to whichever object
existed at collection time — the FIRST import. Every subsequent test's fresh
`_install_stub_modules()` call rebuilt a NEW object for the production code to check
against. The two sides of the `isinstance()` check were quietly drawing from two
different "real" `openai` modules, and every earlier fix (steps 1 and 2) was necessary
but not sufficient — they made the module genuinely real again, but not genuinely THE
SAME real module used elsewhere.

The debugging trap: checking `hasattr(module, 'InternalServerError')` (presence) is not
the same claim as checking object identity (`module.InternalServerError is other_
module.InternalServerError`). Two rounds of debugging confirmed presence and moved on,
because presence is the natural thing to check first and it looked conclusive.

## The rule

**When a fixture re-imports a real dependency to undo another test's stub, make the
re-import idempotent — check whether what's cached is already the real thing before
purging and re-importing.** A purge-and-reimport that runs unconditionally on every test
invocation doesn't just waste work; each execution mints fresh class objects, and any
code elsewhere holding a reference to an EARLIER execution's classes will silently fail
identity/`isinstance` checks against the newest one. The fix is one guard: `if hasattr
(cached_module, 'known_real_attribute'): return` before the purge. Once genuinely
imported, leave the module alone for the rest of the process so every reference —
the test file's own top-level import, and any freshly-imported production code under
test — resolves to the exact same object.

## Why it generalises

This is not specific to `openai`, `httpx`, or Python's mock-module test pattern. Any test
suite that undoes another test's `sys.modules` stub by deleting-and-reimporting a real
dependency is vulnerable the moment more than one test in the run triggers that undo path
— the second undo silently orphans anything that captured a reference from the first.
The bug is invisible in isolation (run the one test file alone, it passes — the "second
undo" never happens) and appears only when interleaved with the polluting file in a full
suite run, which is exactly the shape that makes it look like flaky test order rather
than a deterministic identity bug. The generalizable check, whenever a test debugs an
`isinstance`/`is` failure against something that "should obviously match": stop checking
whether both sides have the expected attribute, and check whether they are literally the
same object.
