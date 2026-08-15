# A detector nobody tested detects nothing — and reports that as health

## Symptom

An estate had built five monitors for the specific defects that had embarrassed it in front of a
retail buyer. Each was well-written: careful docstrings, explicit refusal to call an empty window
healthy, thresholds justified in prose. A full sweep on 2026-08-15 returned:

```
PASS           check_liveness
COULD_NOT_RUN  chinese_error_speech        only 0 real assistant turn(s) in the last 1d
COULD_NOT_RUN  device_tool_call_outcomes   only 0 tool dispatch(es) in the window
COULD_NOT_RUN  unprompted_speech           only 0 real assistant turn(s) in the last 1d
COULD_NOT_RUN  wake_to_reply_lag           only 0 turn(s) in the last 1d
COULD_NOT_RUN  deployed_vs_repo            server1: Permission denied
```

Nothing was broken, alarming, or red. Every monitor was behaving exactly as designed. Between them
they had answered **nothing at all**, and had been answering nothing for as long as anyone had been
looking.

Investigating each one individually:

| detector | why it could never fire |
|---|---|
| all four archive-backed | 1-day window against traffic that arrived on 14 days out of ~21, so the window was usually empty |
| solicitation detector | the mechanism it existed to catch injects a **fake user turn**, so its "did a human speak first?" test said yes |
| same detector, separately | required an end-of-utterance record *before* the reply — but that record is a **latency measurement written after** the reply it describes |
| tool-failure detector | gated its pass on the volume of a **different, older** telemetry stream than the failure signal it reported on |
| deploy-drift detector | built its SSH target as `user@user@host` — permission denied on every server, every run |

Four of five could not detect the thing they were named after. The fifth passed for a real reason,
but could not have known the difference.

## What actually happened

Each detector was written, reviewed, committed, and scheduled. **None was ever run against a case
it was supposed to catch.** Correctness was established by reading the code, and the code was
correct — about a mechanism the author had assumed rather than observed.

The two most instructive failures were about *what a field means*, not about logic:

- The solicitation detector asked "is there a `role: user` row before this reply?" A `role: user`
  row is not evidence a human spoke. In this system, user turns broke down as **29,465
  `text_input`** (the team's own harness), **1,181 `device_speech`** (an actual person), and **24
  `server_injected`** (the server writing a turn to prompt itself). Our own traffic outnumbered
  real speech 25:1, and the defect being hunted lived entirely in the 24.
- The other asked "is there an end-of-utterance record before this reply?" — reasonable, until you
  read the record: it is emitted *after* the response, carrying `voice_to_response_ms=5570.9`. Its
  own payload proves the speech preceded the reply by six seconds. Being written last, it could
  never satisfy an ordering test on the first turn of a session, which is exactly where the
  judgement was made.

Both detectors were **logically sound and empirically wrong**, because a field's name was trusted
over its behaviour.

## The rule

**A detector is not done when it is written. It is done when it has fired on a real positive.**

Before trusting any check, answer three questions with evidence rather than reasoning:

1. **Has it ever produced a non-trivial verdict?** Not "does it pass" — has it ever said anything?
   A long run of `could_not_run`, or of green on an empty window, is the signature of a check that
   cannot execute. Absence of findings is not evidence of health unless the check can also
   demonstrate it *ran*.
2. **What would make it fire, and have you seen that happen?** If you cannot construct the positive
   case, you have written an assertion, not a test. Feed it a known-bad input — a recorded
   incident, a synthetic replay — and watch it go red.
3. **For every field it keys on: what does that field actually contain?** Not what its name
   suggests. Count the distinct values in production. The two failures above were both a field
   whose name was right and whose semantics were not.

**And check the gate measures the same thing as the signal.** One detector's confidence gate
counted a *pre-existing* telemetry stream while its finding came from a *newer* one, so a server
whose failure reporting was dead still cleared the gate at full volume. A gate keyed to a different
signal than the alarm is decorative.

## Why it generalises

This is not about monitoring infrastructure. It is the general shape of **any code whose success
condition is silence** — alerts, validators, guards, linters, permission checks, fraud rules,
health probes, test assertions that only fail on regression.

Ordinary code announces its own brokenness: you run it, and it does the wrong thing visibly. Code
whose output is *nothing* has the opposite property — broken and working are byte-identical from
outside, and the broken version is *cheaper*, because it never produces a finding anyone has to
investigate. So it survives review, survives scheduling, and accrues trust in proportion to how
long it has been quiet.

The economics are worth stating plainly: a detector that cannot fire is **worse than no detector**.
No detector leaves a known gap. A silent detector fills that gap with a green light, and the
attention that would have gone to the risk goes somewhere else. Every one of the defects above had
a monitor, and the team believed it was covered.

The corollary for review: **you cannot review a detector by reading it.** Reading confirms it is
consistent with the author's model of the system. The failure mode is that the model is wrong — and
only running it against a real positive tests the model rather than the code.
