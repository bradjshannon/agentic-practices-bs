# An error message names a subsystem — check whether the timing even permits it

**2026-08-20, a voice-assistant server estate (S2), server conductor run 58.**

## Symptom

An appliance greeted about 1 in 60 device connections with silence. The server's only artefact was
one line:

```
core.providers.tts.base -ERROR- 语音生成失败: Hi, how can I help you?，请检查网络或服务是否正常
```

— *"speech generation failed … please check whether the network or service is normal."* Two
`504 Deadline Exceeded` errors sat in the same log window, on a preview model, which corroborated
the story beautifully. The obvious read was an upstream timeout.

That read was wrong, and it had survived for the entire life of the feature.

## What actually happened

The retry loop that emits the line is only reachable after **five exhausted attempts**:

```python
max_repeat_time = 5
while max_repeat_time > 0:
    try:
        audio_bytes = asyncio.run(self.text_to_speak(text, None))
        if audio_bytes:
            ...; break
        else:
            max_repeat_time -= 1          # <-- logs NOTHING
    except Exception as e:
        logger.warning(f"...失败{5 - max_repeat_time + 1}次: {text}，错误: {e}")
        max_repeat_time -= 1
else_branch_exhausted:
    logger.error("语音生成失败: ... 请检查网络或服务是否正常")
```

Timestamps put the ERROR **6–9 ms** after the connection's preceding message, across three separate
failures. **Five network round trips do not fit in 6 ms.** Whatever happened, the network was not
in it.

That one arithmetic check turned a vague "flaky TTS" into a falsifiable prediction: *if no exception
is ever raised, there must be exactly zero per-attempt warnings.* Measured on the live container:
**0 warnings, 8 final errors, 0 successes.** Confirmed — every attempt took the silent `else`.

Reading down the call chain found the rest in one step: the configured provider is a *streaming*
provider, and its `text_to_speak` is a stub —

```python
async def text_to_speak(self, text, output_file):
    """Not used for SINGLE_STREAM — synthesis runs via _synthesize_stream."""
    return None
```

— while the caller used the **non-streaming** entry point. The feature could never have worked. The
apparent "1 in 60" was how often it was *attempted*; the failure rate when attempted was **100%**,
which the log itself proved: the success line appeared **zero** times in the entire log.

## The rule

**When a log line blames a subsystem, check whether the observed timing permits that subsystem to
have been involved — before you investigate it.** Latency is a cheap, hard constraint and it is
usually already in the log you are reading. Network I/O has a floor; disk has a floor; a retry loop
has a floor equal to its attempts times that floor. If the elapsed time is below the floor, the
named subsystem is excluded, no matter how plausible the message.

Two corollaries earned in the same hour:

- **A failure path that cannot log is worse than a noisy one.** Of the two exits from that loop,
  one described itself and one said nothing — so the *only* surviving evidence came from the branch
  that did not run. The message wasn't merely unhelpful, it was actively misdirecting, and it
  misdirected for as long as the feature existed.
- **Compute rates against the right denominator.** "7 failures out of 438 connections" read as a
  1.6% flake. The correct denominator was attempts, not connections, and the real rate was 100%.
  A rate against the wrong denominator does not look uncertain — it looks precise, and it downgrades
  a total outage to a nuisance.

## Why it generalises

Error strings are written **at the point of despair**, by an author guessing at a cause they could
not observe — and they are then read as evidence *about* the cause. Nothing keeps them honest,
nothing tests them, and they long outlive the conditions that inspired them. So the blame in an
error message is best treated as the original author's hypothesis, carrying roughly the weight of a
code comment.

The timing check is valuable because it is **independent of the message and nearly free**: it uses a
different channel (elapsed time) than the one under suspicion (the author's prose), so it cannot be
fooled by the same mistake. That independence is the whole point — the same reason a control must
not share the treatment's confounds.

Watch for the aggravating pattern that nearly landed here: **an unrelated failure in the same
window that corroborates the wrong story.** Two genuine `504 Deadline Exceeded` errors, on different
text, made "upstream timeout" feel confirmed. Nearby evidence pointing the same way is not
independent evidence; it is a coincidence with good timing.

Related: `a-cannot-measure-claim-is-a-claim-about-your-tooling-2026-08-19.md` and
`fixed-at-the-one-site-is-a-claim-about-the-call-graph-2026-08-16.md` — all three are the same
family, where a confident sentence stands in for a measurement nobody took.
