# A success regex matched the word "ok" in a "not started" reply (2026-08-20)

**A pass/fail classifier over tool output, whose raw output is never printed, cannot be audited by
anyone — including the person who wrote it.** It reports a clean number either way.

## What happened

A hardware probe's read reliability was in question: an earlier module had measured ~1-in-3
per-register success, and the operator had since replaced it. To check whether the replacement
helped, the agent called the device's probe tool 15 times and counted:

```powershell
if ($r.text -match 'FOUND|OK') { $ok++ } else { $fail++ }
```

It reported **15/15 clean** and resolved the tracking card on that basis.

The tool's actual reply, every time, was:

```
is_error=False   text=ok: not started
```

`-match 'OK'` is case-insensitive and matched the `ok` in `ok: not started`. Every "success" was the
probe reporting that **it had never run**. The measurement established that the tool was reachable.
It said nothing whatsoever about the thing being measured.

It was caught by the operator asking *"how did you measure the read rate when it's not connected"* —
not by any check the agent had in place. The card had to be reopened and a written claim retracted.

## Why the shape is dangerous rather than merely wrong

- **The failure direction is silent and green.** A classifier that is too *strict* produces noisy
  failures somebody investigates. One that is too *loose* produces a clean number nobody questions.
  Only the second kind ships.
- **The raw output existed and was discarded.** The loop printed a sample only on the `else` branch,
  so a classifier that never took the `else` branch printed nothing at all. The evidence that would
  have exposed it in one second was fetched, evaluated, and thrown away 15 times.
- **Substring matching on status prose is a category error.** `ok`, `OK`, `found`, `pass` and `done`
  all appear inside negative and not-yet-run replies (`ok: not started`, `not found`, `no OK
  response`). A status word is not a status.
- **Repetition reads as corroboration and is not.** 15 identical results felt like a strong signal.
  They were 15 draws from a constant, which is exactly what a broken classifier produces.

## The rule

**Print the raw output of at least one sample before reporting any count derived from it**, and put
that sample in the write-up next to the number. If the sample cannot be shown, the count is not
evidence.

Then, in order of strength:

1. **Assert the positive shape, never the absence of a negative one.** Match what a *success*
   uniquely contains (`FOUND at 0x`, a register readback value), not a word that also appears in
   failures.
2. **Give the classifier a negative control.** Run it against a reply you know is a failure and
   confirm it counts as one. A classifier never observed rejecting anything is not known to reject
   anything.
3. **Make "did not run" a third outcome, not a silent member of either bucket.** `ok / fail /
   didn't-run` is the honest trichotomy; forcing a not-started into pass-or-fail guarantees one of
   them is a lie.

## The generalisation, which is the part worth carrying

This was the **second instance in the same session**, in different clothing. Hours earlier the same
agent reported "no BindingEvent was emitted for the physical press" — a conclusion drawn from a
console view that had been truncated at 20 rows. The event was there the whole time.

> **A view of the evidence is not the evidence.** Truncation, a lossy regex, a filtered query and a
> summarised count all produce something that reads exactly like a measurement and is not one. In
> both cases the underlying data was correct, retrievable, and had already been fetched.

The tell is available before you publish, and it is one question: *can I show the raw thing this
number came from?* If the answer involves re-running anything, the number is not yet evidence.

## Related

- `measure-the-instrument-before-the-effect.md` — the instrument here was the classifier, not the
  probe, and it was never measured.
- `a-loud-instrument-is-not-data-either-2026-08-02.md` — the sibling failure: a confident non-null
  reading that is equally uninformative.
- `a-check-that-cannot-fail-reports-holds-forever-2026-08-01.md` — the same defect one level up, in
  a check rather than in an ad-hoc count.
- `instrument-flat-reading-is-not-a-null-result-2026-08-08.md` — 15 identical results are a flat
  reading, and flatness is a thing to explain rather than to trust.
