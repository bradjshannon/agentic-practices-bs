# A subagent's negative result is not evidence — verify its search scope

## Symptom

A user asked whether a topic had been discussed before. I dispatched a subagent to search prior
session transcripts. It ran ~20 query variants and reported, clearly and with appropriate hedging,
that **nothing existed** — no mention of the workspace, the vendors, or the protocol in any prior
session.

I relayed that to the user as fact, and added a confident causal story on top: *"So I didn't forget
it; it was never captured. That's the gap, and it's mine to close."*

The user's reply: **"This is literally impossible. the previous server conductor session and the one
prior are about exactly this."**

## What actually happened

The search tool had an `include_archived` parameter. It defaults to false. Nearly every relevant
session was archived.

The subagent searched a small fraction of the corpus and correctly reported finding nothing *in what
it searched*. The defect was not in its search terms — its terms were good — it was that neither of
us checked what population those terms were applied to.

When I ran the same one-word query myself **with `include_archived: true`**, it returned ten
sessions, including one whose title was the exact topic and whose snippet was the answer.

## The rule

**A negative from a search whose scope you did not verify is not evidence of absence.** Before
relaying "it isn't there," establish what "there" was:

- What population did the query actually run against — and what does the tool exclude *by default*?
- Would a known-present item have been found? Run one positive control: search for something you are
  certain exists. If it does not come back, the negative is worthless.
- Does the tool have a scope/filter/archive/date parameter that was left at its default?

And when delegating: **state the scope requirement in the prompt**, because the subagent cannot know
what it does not see. "Search X" invites a default-scoped search. "Search X, passing
`include_archived: true`, and confirm with a positive control" does not.

## Why it generalises

This is the same failure as a check that cannot run reporting nothing — byte-identical output to a
check that ran and found nothing — but it is *worse* under delegation, for two reasons.

**The report launders the gap.** A subagent returns prose, not a query plan. Its careful hedging
("this appears to be new territory, or it happened somewhere this search doesn't reach") reads as
epistemic virtue and made me *more* confident, when the honest reading was that it had named its own
blind spot and neither of us followed the pointer.

**A negative invites a causal story, and the story cements the error.** Told "no results," I
immediately explained *why* there were no results and assigned myself a remedy. That narrative made
the finding feel processed and closed. A positive result gets checked because it can be inspected; a
negative gets explained, and explanation feels like verification.

Practical asymmetry worth holding: **a subagent's positive findings are cheap to verify and its
negative findings are not.** Spot-check a positive by opening the thing it found. A negative has
nothing to open — so the only available check is on the *method*, which means the method is the
thing you must ask about before you believe the result.
