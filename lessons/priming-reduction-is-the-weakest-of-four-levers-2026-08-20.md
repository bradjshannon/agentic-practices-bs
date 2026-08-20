# Priming reduction is the weakest of the four levers (2026-08-20)

**Shrinking the launch payload is the lever everyone reaches for and the smallest one there is.**
Measured on a single long conductor session, the ranking is: **fewer requests > smaller tool
results > shorter output > pruning priming.**

## The measurement

One session, 689 requests, prefix growing 79k → 564k tokens.

| | tokens | cost-weighted share* |
|---|---:|---:|
| cache **read** | 234,427,784 | **83.8%** |
| output | 608,818 | 10.9% |
| cache creation | 1,180,368 | 5.3% |
| fresh input | 1,378 | ~0% |

\* ratios read 0.1× / creation 1.25× / output 5× — illustrative, but the ordering is robust to any
plausible pricing.

## What the numbers say that intuition does not

**The forced launch payload inverts in importance.** It was ~43k tokens: 54% of the prefix at
request 1, and about **13% amortized** (43k × 689 ≈ 29.6M of 234.4M cache-read). A trim of ~12k of
low-value catalogues looked like "28% of the launch payload" and is **~3.5% of the bill**. The
framing that made it sound big — share of the *first* prefix — is the wrong denominator.

**Prefix GROWTH dominates prefix FLOOR.** 485k of the final 564k prefix was accumulated
conversation and tool results. Every fat tool result is re-read by every later request in the
session, so cost is `size × requests_remaining`. A 12k log dump at request 200 costs ~5.9M — about
a fifth of what the entire launch payload cost across the whole session, from one careless command.
**A large tool result is not a one-time cost; it is a subscription.**

**Request count is a raw multiplier on everything.** 689 requests for ~150 messages. The whole
prefix is billed once per request, so halving round-trips halves the bill with no pruning at all.
At a 340k mean prefix, each avoidable extra request costs ~34k cache-read units. Chatty
verify-then-act-then-re-verify patterns are the expensive habit, not long documents.

**Output is billed at a steep multiple.** 608k output tokens produced 10.9% of the weighted cost
against 234M cache-read tokens producing 83.8% — per token, writing was ~50× more expensive than
re-reading the prefix. A brevity rule is defending a real line item, not tidiness.

## The rule

Rank optimisations by `size × remaining_requests`, not by size:

1. **Cut requests.** Batch independent tool calls into one message. This is the only lever that
   scales the whole bill at once.
2. **Cut tool-result volume** — especially early, when many requests remain. Ask for the field, not
   the record; the conclusion, not the log.
3. **Cut output length.**
4. **Prune priming** — real, and the smallest of the four.

## Why it generalises

The estate that produced this measurement had spent a full session restructuring a 1831-line brief
down to 1011 lines, treating priming as the cost problem. That work was worth doing, but it is lever
#4, and the same session then spent far more on single-tool-call messages and unfiltered log dumps
while believing it was economising.

**The trap is that priming is the visible cost and the accumulating costs are invisible.** You can
open the brief and see 21k tokens. You cannot see that a device-log dump you already forgot is being
re-read four hundred more times. Anything a system asks you to optimise by *looking* will point at
the floor and miss the growth.

## Related

- `read-your-own-context-from-the-transcript.md` — the same source (per-request `usage` records)
  answers this; nothing extra had to be instrumented.
- `a-success-regex-matched-the-word-ok-in-a-not-started-reply-2026-08-20.md` — same session; the
  first framing here ("28% of the launch payload") was another count reported against the wrong
  denominator.
