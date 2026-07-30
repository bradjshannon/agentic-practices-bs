#!/usr/bin/env python3
"""Controls for hardware_hedge_guard.py, in BOTH directions.

The positive cases are the two real sentences that caused this hook to exist, verbatim from the
2026-07-30 session. The negative cases are each a false positive that would have discredited it --
a guard that cries wolf gets routed around and takes its true positives with it.

⚠️ This suite imports the hook FROM THIS DIRECTORY by relative path, deliberately. Four other
suites in here resolve their target via `~/.claude/hooks/` and therefore verify the INSTALLED copy
rather than the banked one, so another machine can pull a broken hook and still get green. Keep
this one relative.

Run: python hardware_hedge_guard_test.py    (exit 0 = all pass, 1 = something failed)
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    spec = importlib.util.spec_from_file_location(
        "hardware_hedge_guard", os.path.join(HERE, "hardware_hedge_guard.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# (name, said, tool_results, tool_calls, want_block)
CASES = [
    # ---- POSITIVE: the sentences that cost Brad a round-trip ----
    ("POS 1 the real NIMBE mic sentence",
     "Still unverified, and it's a hardware fact I can't settle from code: whether the two "
     "ES7210 M-slots are two physically distinct PCB mics.",
     "some grep output here", 1, True),
    ("POS 2 the real OMOBE mic sentence",
     "OMOBE's mic is unverified. So I can't currently confirm OMOBE captures audio at all.",
     "afe_active False", 1, True),
    ("POS 3 hedge about a pin",
     "The /OE pin 19 wiring is not verified on either '245.",
     "reading a header", 1, True),

    # ---- NEGATIVE: each is a false positive that would discredit the hook ----
    ("NEG A an authority WAS consulted this turn",
     "OMOBE's mic count is unverified from the schematic.",
     "notion-fetch: AI-VOX3 Hardware Source of Truth ... single mic", 1, False),
    ("NEG B software hedge, no physical noun",
     "The wire contract is unverified and the upload client cannot confirm the schema.",
     "pytest output", 1, False),
    ("NEG C hedge and hardware noun in DIFFERENT sentences",
     "The merge order is not verified. Separately, the ES7210 feeds four channels.",
     "grep", 1, False),
    ("NEG D a QUESTION, not an assertion",
     "Can I confirm the mic count from the datasheet, or is that unverified?",
     "grep", 1, False),
    ("NEG E blockquoted -- Brad or a doc speaking",
     "> the mic is unverified?\nI checked and it is a dual-mic board.",
     "grep", 1, False),
    ("NEG F no tool calls (pure conversation)",
     "The mic count is unverified and I cannot confirm the PCBA layout.",
     "", 0, False),
    ("NEG G honest BOUNDED hedge, not an absolute",
     "Not yet measured on this board: the mic gain. I will read the ADC next.",
     "grep", 1, False),
]


def main() -> int:
    m = load()
    failures = 0
    for name, said, results, calls, want in CASES:
        got, hedges = m.evaluate(said, results, calls)
        ok = got == want
        if not ok:
            failures += 1
        detail = f"  hedge={hedges[0][:70]!r}" if hedges and not ok else ""
        print(f"{'PASS' if ok else 'FAIL'}  {name}: would_block={got} (want {want}){detail}")

    # The override is handled in main(), not evaluate() -- assert the token is still DETECTED so a
    # regression in the regex cannot silently make the escape hatch unreachable.
    tok = bool(m.OVERRIDE.search("The mic count is unverified. hardware:unverified-ok"))
    print(f"{'PASS' if tok else 'FAIL'}  OVERRIDE token is detectable: {tok} (want True)")
    if not tok:
        failures += 1

    total = len(CASES) + 1
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
