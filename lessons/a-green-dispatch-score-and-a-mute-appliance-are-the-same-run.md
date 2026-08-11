# A green dispatch score and a mute appliance are the same run

**Symptom.** An A/B/C/D test harness scored a voice-assistant's deterministic fast-path arm
**15/15 correct** on the morning of 2026-08-11. That same afternoon a human tester found that this
exact arm, in production, executed the command and then went **completely silent** — no reply, no
error, the unit unresponsive until a 3-minute connection timeout. Both results were accurate.

**What actually happened.** The harness asserted *which tool was dispatched*. Dispatch was correct
every single time — the appliance really did receive and execute the right command with the right
arguments. What the harness never asserted was that **a reply came back to the user**. The reply
path was raising an `AttributeError` into a `concurrent.futures` Future that nothing ever read, so
it produced no log line, no exception, and no audio. A test suite measuring the first half of the
turn certified the whole turn.

**The rule.** **For any user-facing pipeline, assert the last observable output, not the internal
step you happen to have instrumented.** For a voice product that means: did audio come back? For a
request/response API: did a response body reach the client? "The correct internal call was made" is
a proxy, and a proxy can be perfect while the product is broken. Before trusting a passing suite,
ask: *if the final output vanished entirely, would any test in this suite fail?* If not, the suite
measures a stage, not the product.

**Why it generalises.** This is the proxy-vs-capability failure in its most flattering costume:
the metric isn't merely uninformative, it's *actively reassuring*, and it's reassuring precisely
about the component that's broken. The stronger the internal instrumentation, the more confident
the wrong conclusion — a team with a rich dispatch-telemetry dashboard is *more* likely to believe
the arm is healthy, not less. Any pipeline where an intermediate stage is easier to instrument than
the terminal output will drift into measuring the intermediate one, because that's where the data
already is.

**Corollary, from the same incident.** A bare `executor.submit(fn)` with no done-callback and no
`.result()` is not an error handler; it is an **error eraser**. The bug was invisible rather than
merely unfixed for as long as it existed, because the traceback had nowhere to go. Every
fire-and-forget submission is a place a live failure can hide indefinitely — attach a callback that
logs, even if you never intend to read the value.
