# A parity test comparing two copies is blind to a bug they share

## Symptom

A fix landed in the shared kernel (`conductorkit/core.py`) correcting how a resolved item with an
unanswered embedded decision is classified. A dedicated lineage-parity test existed specifically to
stop two forks of the renderer from drifting, and it was green on that logic. The bug was
nevertheless still present in **both** forks.

## What actually happened

There were **three** carriers of the same logic, not two:

1. the shared kernel, imported by the live production entry point — **fixed**
2. fork A's `status_page.py` — stale inline copy
3. fork B's `status_page.py` — stale inline copy

The parity test compared **2 against 3**. They were wrong *identically*, so every assertion passed.
The test was doing exactly what it was written to do — detect divergence — and divergence is the
wrong predicate for this defect. Two copies that drift apart get caught; two copies that are
equally stale relative to a third authority do not.

Worse, the test's success was actively reassuring: a green parity run reads as "these are in sync,
therefore correct," and the second clause does not follow from the first.

## The rule

**A consistency check between replicas cannot detect a fault common to all replicas.** If you have
N copies of a rule and a check that compares copies pairwise, the check's blind spot is exactly the
class of bug that is uniform across them — which includes the most common one, *"the authority moved
and none of the copies followed."*

When you write a parity/consistency test, name the **authority** explicitly and assert against it,
not against a sibling. If there is no authority — if the copies genuinely are peers — that is itself
the finding: the design has no single source of truth, and the test is measuring agreement rather
than correctness.

## Why it generalises

This is the structural argument for single-authority-not-mirrored-copies, arriving from the test
side rather than the design side. The usual case against mirroring is drift; this is the case
against mirroring *even when drift is being actively policed*, because the policing mechanism has a
hole exactly where the mirroring is working best.

It applies to any replicated invariant with a checker: config mirrored across environments and
diffed against each other; a schema duplicated in two services with a contract test comparing the
two copies; documentation stating a rule in several places with a lint that only checks they match;
translated strings compared for structural parity while all sharing one mistranslation.

The diagnostic question, cheap to ask and rarely asked: **"if this fault were present in every copy,
would this check still pass?"** If yes, the check is measuring agreement, and you need a separate
assertion against whatever is actually authoritative.

## See also

`single-authority-not-mirrored-copies-2026-08-01.md` — the same conclusion reached from the design
side. `a-check-that-cannot-fail-reports-holds-forever-2026-08-01.md` — the adjacent failure, where a
check is structurally incapable of firing at all rather than blind to one class.
