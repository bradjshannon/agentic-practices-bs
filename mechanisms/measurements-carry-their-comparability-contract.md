# Measurements carry their own comparability contract

**Mechanism:** `mechanisms/scripts/measurement_contract.py`
**Class:** Structural — the bad state (a stored number with no comparability contract) is
unrepresentable; `Measurement.__post_init__` refuses to construct one.
**Origin:** 2026-08-01. Design credit: the operator.

## The failure it prevents

A bare integer looks comparable to another bare integer, and nothing in it objects. Twice in one
day, on one project, two numbers were subtracted that should not have been:

- **The sign inverted.** "Enabling the wakeword FREED 22,640 B of internal DRAM" — two readings
  differing in wake-state *and* uptime *and* session activity. Controlled, the wakeword **costs**
  ~16.9 KB. The claim stood four days and was used for capacity planning.
- **A false cause, inside a warning about stale claims.** An ADR gate compared 2,863 B (board
  "live") against 19,075 B (board idle) and attributed the gap to four commits — none of which
  could have produced it; one moved the wrong way. Written by the same agent that had banked the
  lesson about uncontrolled before/afters an hour earlier.

Both were written carefully. Neither number carried what would make a later number comparable to
it, so nothing *could* object. **Prose discipline ("remember to note the conditions") is Voluntary
class and failed within the hour of being written down.**

## The design, and why each decision is not arbitrary

**The contract is stated at STORE time, by the author.** They are the only one who still knows
what they controlled. Not inferred later; not enumerated up front by whoever designed the schema,
who cannot know which conditions mattered for someone else's reading.

**`comparable_when` IS the checker.** There is no separate comparison rule to drift from it —
`compare()` reads the field. A key you forgot is not an omission somebody has to notice; it is a
mismatch the tool reports.

**Three verdict states, because "not refused" is not "valid".**

| state | meaning |
|---|---|
| `REFUSED` | a named condition mismatches, or a record declares itself confounded |
| `NO-KNOWN-OBJECTION` | everything checked matched. Deliberately *not* worded "comparable", and it lists what was checked so the bound is visible |
| `UNKNOWN` | a confounder known *now* that neither record captured |

That third state answers the objection that killed the first draft — *"we can't explain every
possible confounding variable, pre-emptively."* True, and unnecessary: **you don't need foresight,
you need discovery to propagate backwards.** The registry grows; each measurement records what was
known when it was stored; learning that a condition matters retroactively demotes every earlier
reading that never recorded it, rather than leaving it looking clean.

**The UNION of both contracts must hold, not the intersection** — a comparison is valid only if
both authors would have accepted it. Intersection lets one lazy record erode a careful one, which
is exactly how a casual number pasted into a doc poisons a rigorous one.

**Instrument and subject always match, whatever the contract says.** This is the failure that hides
best: two tools reporting "free internal memory" through different capability masks gave 2,475 B
and 8,491 B minutes apart on one healthy board. That looks precisely like a memory collapse.

**`known_confounded_by`** is the narrow legitimate blacklist: a confounder you know matters and
know you did *not* control. That is knowledge, not absence of it, so it refuses rather than
flagging unknown.

**Citations, not repetition.** The operator: *"as long as there is a chain that leads back to the primary
source... once cited, we don't need to repeat the citation every time."* A doc carries `[m:<id>]`
once instead of restating conditions, and `resolve_citations()` turns a stale doc number from
merely suspect into *checkable*. A dangling citation is reported, never silently dropped.

## Porting it

Only one thing is project-specific: the registry.

```python
import measurement_contract as mc
mc.set_registry({"uptime_s": "2026-08-01", "session_active": "2026-08-01"})
# or mc.load_registry("confounders.json")
```

Everything else — contract, union rule, three states, retroactive demotion, citations — is
domain-independent. **If a project cannot express its confounders as entries in that dict, the
abstraction is wrong**, and finding that out fast is the point of keeping the seam this narrow.

## The ceiling, stated so nobody oversells it

It forces the contract to **exist**, not to be **right**. `comparable_when=["build"]` on a value
that actually depends on uptime will happily compare two incomparable things — the same ceiling
`evidence_with_claim` has. It is still a strict improvement: a wrong contract is visible and
falsifiable, whereas the absent contract that caused both incidents was invisible. And being made
to write "comparable to anything on this subject" tends to make you notice you are claiming
something strong.

## Tests worth copying, not just the code

`myproject-firmware/tools/test_measurement.py` — 28 checks built on the two **real** pairs above: one
properly controlled (must be **accepted**) and one confounded (must be **refused**). The accept
case is load-bearing: a checker that only refuses would pass a reject-only suite by refusing
everything.

Two harness bugs found while writing it, both of the exact class the module targets: appended
tests landed after a trailing `sys.exit()` **twice**, and `ALL PASS` printed over tests that never
ran; and `sys.exit()` inside an `atexit` handler is swallowed, leaving a failing suite exiting 0.
Hence the printed check **count** — a suite that silently shrinks is otherwise indistinguishable
from one that passes.

Related: [[../lessons/an-uncontrolled-before-after-inverted-the-sign-2026-08-01]],
[[../lessons/measure-the-instrument-before-the-effect]], [[a-check-that-exercised-nothing-must-fail]].
