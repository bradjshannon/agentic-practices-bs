# A queue-scan summary drops the caveat that blocks the fix (2026-09-01)

## Symptom

A subagent was asked to scan a project's open-issues register and return a prioritized list of
"actionable" items — already root-caused, ready to ship. It returned two items described as
one-line, low-risk fixes. Both, on reading the primary source in full, turned out to carry an
explicit, previously-recorded instruction not to apply exactly that fix without a human
reconfirming first. The second instance was caught only because the first had already raised
suspicion — the same failure fired twice in one run, back to back, before the pattern was
recognized as a pattern rather than one unlucky read.

## What actually happened

The scan agent's brief asked it to summarize a large, discursive issues file — hundreds of lines
per entry, written as a running log with corrections, reversals, and disputes layered in over
weeks. For each entry it extracted: what the defect is, why it's "actionable now" (root-caused,
etc.), and effort. Both flagged items had genuinely been root-caused. What the summaries dropped
was a load-bearing sentence sitting a few paragraphs later in the *same entry*:

- Item A: "**Deliberately NOT fixed in this run:** flipping the precedence changes which language
  a device is told to speak, fleet-wide... it needs its own change with device-level verification,
  not a drive-by."
- Item B: "**NOT FLIPPED.** The [prior] meeting agreed the unit SHOULD [do the behavior the fix
  would remove]... disabling it outright conflicts with that." Followed by a DISPUTED annotation:
  "Do not apply... without [the human] reconfirming directly."

Neither sentence was buried — both sat within the same YAML/markdown block the summary was built
from, a few hundred words past the root-cause paragraph the summary quoted. The compression step
kept "what's wrong" and "why it's fixable" and dropped "why it hasn't been fixed," because that
information lives in a different part of the entry's shape (a caveat/decision paragraph, not the
root-cause paragraph) and a summarization pass optimized for "extract the actionable fix" has no
structural reason to preserve a paragraph that argues against action.

The catch mechanism was cheap and already available: before touching either file, the full
original entry was read in the actual issue register, not just the subagent's extraction. Both
caveats were found in under a minute each, sitting a few lines below the sentence the summary had
quoted.

## The rule

**A "ready to fix" claim from a compressed source is a claim to re-derive by reading the entry
whole, not a claim to act on directly — because a summarizer optimized for "is this actionable"
has a structural reason to drop the sentence that says it isn't.** This is not about distrusting
subagents generally; the root-cause work itself was accurate both times. It is specifically that
*a summary's shape encodes what its author was looking for*, and "why this hasn't shipped yet" is
exactly the kind of sentence that gets cut when the extraction target is "the fix," not "the
decision."

Cheap, mechanical version of the check: before implementing anything a summary calls "ready" or
"low-risk," grep the *primary* source for words a caveat is likely to use — "not fixed",
"deliberately", "do not", "without confirming", "disputed", "still open" — in the neighborhood of
the cited root cause, before writing code.

## Why it generalizes

This is a special case of a broader shape: **any compression step (a subagent summary, a
changelog entry, a status dashboard, a one-line ticket title) is built to answer a specific
question, and a caveat that answers a different question than the one being asked gets dropped
first — not because it's less true, but because it's less relevant to the compressor's target.**
A "ready to ship" extraction drops "why it isn't shipped." A "here's what changed" extraction
drops "what we decided not to change and why." The fix is the same in every case: read the
primary source for anything a compression pass was asked to act on, especially when the action is
irreversible or affects something fleet-wide/shared — the caveat that would have stopped you is
disproportionately likely to be exactly the sentence a summary optimized for "actionability" cuts.
