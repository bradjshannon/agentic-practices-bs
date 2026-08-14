# Relay the operator's words; your reading of them goes below, marked as yours

**Symptom.** A conductor relaying an operator's message to a subagent wrapped it in interpretation:
the message opened *"Read that as:"* and expanded a one-line bench observation into a claim about
which layer a defect had to be in. The operator's correction: *"next time just tell the agent what i
said instead of interpreting."*

Refined by him an hour later into the actual requirement:

> *"add whatever you want, with attribution. but when you farm out work, include my verbatim
> instructions first, and indicate the difference"*

**What actually happened.** The expansion was *defensible* — a competent engineer would have drawn
roughly the same inference. That is what makes this worth writing down rather than filing as a
lapse. The failure is structural, not a wrong reading:

- What the operator said is **evidence**.
- What the relayer thinks it implies is a **hypothesis**.
- Merged into one sentence, the subagent receives the hypothesis wearing the operator's authority —
  and cannot argue with an original it never sees, while being closer to the evidence than the
  relayer is.

The first attempt at a rule here was *"do not interpret"*, and that was wrong too: it would have
discarded framing that is often worth having. The operator explicitly did not ask for that.

**The rule.** In any dispatch brief, the operator's exact words go **first**, quoted and attributed.
Anything you add goes below it, visibly separated and marked as yours. Never merged into one
sentence, and never yours first.

**Why it generalises.** Any relay across an authority gradient has this shape — a manager quoting a
customer to an engineer, an agent quoting a log to another agent, a summary standing in for a
source. The receiving party is usually better placed to interpret the raw evidence than the relayer
is, and can only do so if the raw evidence arrives intact and distinguishable. Separation costs one
line of formatting and preserves the receiver's ability to say *your framing is wrong* — which is
frequently the whole reason to involve them.

The tell that you are doing it wrong: your relay contains *"read that as"*, *"which means"*, or
*"so basically"* attached to a quote rather than standing beside it.
