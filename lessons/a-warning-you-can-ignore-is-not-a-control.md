# A warning you can ignore is not a control

## Symptom

A long, expensive job ran to completion and produced an artifact that was worthless for its stated
purpose. The tool had said so, correctly, in advance — and the run happened anyway.

## What actually happened

An eval harness scored ~2,816 cases against a live server, a five-hour job. Its output is only
meaningful if the run records which model, prompt and TTS produced it; without those, the score
cannot be placed against any other run. The harness knew this and printed:

```text
WARNING run_eval: stack axes NOT RECORDED: prompt_sha, model, tts --
this report cannot be compared with any other run. Pass --prompt-sha --model --tts to fix it.
```

The message is *excellent*: it names the missing values, says what the consequence is, and gives
the exact fix. A downstream `merge()` even refused to pool such reports. And none of that helped,
because the warning scrolled past at second three of an eighteen-thousand-second run, and the
refusal came hours later when the model and server had already moved on.

The operator was an agent following a documented command. It did not notice. Nobody would have.

## The rule

**If producing the bad artifact is still possible, you have written documentation, not a control.**
Rank the options by what they make *impossible*, not by what they *say*:

1. **Fail closed at the earliest point the error is knowable.** Here: refuse the run, exit non-zero,
   before opening a socket or spending a token. The cost of a wrong refusal is one command; the cost
   of a wrong acceptance was five hours.
2. **Make the escape hatch explicit and expensive to hide.** An override is fine — `--allow-uncomparable`
   — provided taking it *stamps the artifact itself*, so a file that outlives its terminal still
   carries the admission. An override that leaves no trace is just the old behaviour with extra steps.
3. **Make the invalid state unrepresentable.** Best of all: if concurrency requires N device
   identities, spell it as "repeat `--mac`" rather than `--workers N`, so you cannot request
   parallelism the system could not honestly provide.

Detecting-and-warning is the weakest tier and it *feels* like the responsible one, because the
message is well written and technically complete. Quality of wording is not enforcement.

**The tell:** you are about to write a policy, checklist item, or runbook line reminding people to
pass a flag the tool already warns about. That is the moment to change the tool instead. A rule that
lives in prose is enforced by attention, and attention is the resource that is always exhausted
first.

## Why it generalises

Every system accumulates advisory signals — lint warnings, deprecation notices, "are you sure?"
banners, dashboard ambers. They share a failure mode: the cost of ignoring one is paid later and
elsewhere, by someone who did not see it. As soon as an automated agent is the operator, "someone
will read it" stops being true in any useful sense; agents follow documented commands and scroll
past stderr exactly as reliably as tired humans do.

The inverse is also worth stating: a control that fails closed will eventually block something
legitimate, and that is the *sign it works*. Design the override at the same time as the gate, and
make the override leave evidence.

Related: `guard-the-selection-not-just-the-reading.md` (a mechanism can guard the right thing about
the wrong input), and `measure-the-instrument-before-the-effect.md`.
