# Measure the instrument before you measure the effect

## Symptom

A team says, correctly, *"I don't know which option is better because there are too many variables
and measurement error is bigger than the effects."* The instinct is to reduce variables — freeze the
config, control the environment, build a cleaner rig. That work is expensive, takes weeks, and does
not tell you whether the thing you care about was ever detectable.

## What actually happened

On a voice-appliance program, nobody could say whether removing a pipeline stage helped. The
available metric was end-to-end response time. Two years of arguments rested on it.

Instead of building a rig, we measured the **noise floor from data already on disk**: group
historical records by (configuration, exact input), keep groups with ≥3 repeats, and compute the
pooled *within-group* standard deviation. Same input, same system, different number — that spread is
the instrument's precision, and it was already sitting in the logs.

The result split the question in two:

| lever | effect | samples needed |
|---|---|---|
| remove one model call | ~1,400 ms | **n = 9–10** |
| shrink the prompt by 10 KB | ~300 ms | **n = 187** |

The first was provable in an afternoon. The second explains why nobody had ever settled it: a 300 ms
effect measured with a 2,000 ms ruler.

And a third finding fell out for free. Two metrics were available; the one everybody quoted had a
within-group sd of 1,953 ms, the one nobody used had 1,036 ms. **Switching metric made the same
experiment 3.5× cheaper** — no instrumentation, no rig, just measuring the right thing.

## The rule

**Before running an experiment, compute the minimum detectable effect from repeats you already
have.** Then say, in advance, which questions are answerable at what sample size — and which are
not answerable at all with the current instrument.

Three corollaries that carried real weight:

- **Separate within-group spread from between-group spread.** Pooling them makes a precise
  instrument pointed at genuinely different things look hopelessly noisy, and invites a rebuild
  that was never needed.
- **When no group has enough repeats, raise — never return zero.** An instrument with no repeats has
  *unknown* precision, not perfect precision. Those two must never render alike.
- **Metric choice is a free variable.** It is usually treated as given. Comparing the noise floors of
  the metrics you already collect can beat any amount of experimental design.

## Why it generalises

Any system logging repeated operations has this data: CI runs of the same suite, requests to the same
endpoint, the same query against the same dataset, retries of the same job. The computation is a
group-by and a pooled standard deviation.

The deeper point is about sequencing. **"Our data is too noisy" is a claim about the instrument, and
it is cheaply testable** — but only if you think to test it. The default move is to argue about the
effect. Measuring the ruler first converts an unfalsifiable complaint into a table of what is
answerable and what is not, which is the difference between a research programme and an afternoon.

It also protects against the opposite error. Had the noise floor come back *larger* than every effect
on the list, the correct action would have been to stop running experiments entirely and fix the
instrument — and we would have known that on day one instead of after a month of results that meant
nothing.
