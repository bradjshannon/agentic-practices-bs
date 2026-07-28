"""Cases for the data-validity Stop check.

Earned 2026-07-28. Across one session I reported, with numbers and tables:
  * "p50 improved ~2.6s, confound excluded"  -- the confound was NOT excluded;
  * "the same device dominates both sides"   -- true of all turns, FALSE of the subset I
    was actually comparing, where the before-sample was ~7 devices over two weeks and the
    after-sample was ONE device on ONE day.
Brad caught both. Neither was a bad measurement -- both were correct numbers with an
unstated comparability problem, which is the failure this check exists to surface.

The ALLOW cases carry the weight: a check that fires on ordinary numbers gets disabled.
"""
import os
import runpy

# Resolve RELATIVE to this file, like the sibling mechanism tests: a test that loads the
# module from ~/.claude would pass while THIS repo's copy was broken -- a test that cannot
# fail for the thing it is guarding.
m = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "data_validity_statement.py"))
evaluate = m["evaluate"]

VALID = ("Validity: before-sample is 7 devices over two weeks, after-sample is one device "
         "on one day, so device and build are confounded with the change; the claim does "
         "not generalize beyond that device and window.")

cases = [
    # -- MUST FIRE: quantitative comparison with no validity statement -----------------
    ("BLOCK", "Baseline p50 was 5187 ms; after the change p50 is 1447 ms, a 3.7s improvement."),
    ("BLOCK", "p95 went from 8.5s baseline to 21.4s after deploy."),
    ("BLOCK", "median latency dropped from 6.2s to 3.6s (n=92 vs n=29)."),
    ("BLOCK", "The fast-path sample shows p50 671ms against 4716ms for LLM turns."),

    # -- MUST NOT FIRE ----------------------------------------------------------------
    # the same claim WITH the statement
    # The statement is a TEMPLATE: its own line, starting `Validity:`. Inline does NOT
    # count -- a fixed shape is checkable, a phrase-detector is a hole (Brad, 2026-07-28).
    ("ALLOW", "Baseline p50 was 5187 ms; after, 1447 ms, a 3.7s improvement.\n" + VALID),
    ("BLOCK", "Baseline p50 was 5187 ms; after, 1447 ms, improved. " + VALID),  # inline
    # single measurements, no comparison -- the common case, must stay quiet
    ("ALLOW", "The page renders 224,386 bytes with no traceback."),
    ("ALLOW", "443 passed, 0 failed."),
    ("ALLOW", "The commit touched 62 files (+5051/-307)."),
    ("ALLOW", "cache mtime 15:40:08.659 vs report mtime 15:40:04.364 - 4.3 seconds apart."),
    # counts that differ but are not a measured population comparison
    ("ALLOW", "Test suite went from 442 passed/1 failed to 443 passed/0 failed."),
    # prose about the concept must not trip it (this file, commit messages, docs)
    ("ALLOW", "We should always state whether a p50 comparison is confounded. " + VALID),
    # a validity statement alone, no claim
    ("ALLOW", VALID),
]

fails = 0
for want, text in cases:
    blocked, _ = evaluate(text)
    got = "BLOCK" if blocked else "ALLOW"
    ok = got == want
    fails += 0 if ok else 1
    print(f"{'ok  ' if ok else 'FAIL'} want={want:5} got={got:5}  {text[:72]}")

# The token must not be satisfiable by a bare word -- it has to name both halves.
lazy_blocked, _ = evaluate("p50 fell from 5187 ms to 1447 ms. Validity: fine.")
print(f"{'ok  ' if lazy_blocked else 'FAIL'} a bare 'Validity: fine' must NOT satisfy the check")
fails += 0 if lazy_blocked else 1

print()
print(f"{len(cases) + 1 - fails}/{len(cases) + 1} passed, {fails} failed")
raise SystemExit(1 if fails else 0)
