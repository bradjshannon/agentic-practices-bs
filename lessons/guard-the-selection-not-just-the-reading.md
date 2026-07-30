# A guard on the reading is not a guard on what got read

**Symptom.** A status page showed **8% context** while the run it claimed to describe was at
**49%**. The number was not stale, not rounded, not a unit error. Every honesty mechanism the page
had was working: it refused to print a bare percentage without its window, refused outright when two
transcripts were live at once, and labelled any reading older than fifteen minutes with its age. The
human caught it only because he happened to know roughly what the real figure was.

**What actually happened.** The page resolved "this run's transcript" from a hard-coded list of two
working directories. The agent had since moved to running from a per-session git worktree under a
third repo. So the lookup found no transcript for the current run, fell back to the newest transcript
under the directories it did know, and reported — correctly, honestly, with all its caveats intact —
**somebody else's idle session.**

Every guard fired correctly. They all guarded the *reading*. None guarded the *selection of what to
read*.

Two more instances of the identical shape surfaced in the same day:

- A firmware routine was documented as "sums `n` bytes, returns uint8_t". True. The doc then stated
  which bytes it summed — and that part was invented, because the function is reached only through a
  pointer and nobody could see a call site. The description of the instrument was right; the
  description of its input was fabricated.
- A web page's sort key ordered its special rows correctly and called `int()` on every other row's
  id, assuming they were numeric. They were not. The correct half of the logic was irrelevant.

**The rule.** *When a check is scrupulous about its answer, ask what population it answered about.*
Honesty machinery clusters around the output — refuse when uncertain, show the units, show the age —
because that is where errors are legible. The input is chosen earlier, usually by a default, a
fallback, or a hard-coded path, and it is chosen silently. So the specific questions are:

- **What is the fallback when the intended input is not found, and is it distinguishable from
  success?** A fallback that returns a real, well-formed value from the wrong source is the worst
  case, because every downstream guard passes.
- **Does the identifier used to select the input still identify the thing?** Paths, working
  directories and machine layouts move. A selector written when the agent lived in one place keeps
  returning *something* after it moves.
- **Would this check still be right if it silently matched nothing?** If "no match" degrades to
  "closest match" rather than to "refuse", it will eventually report a stranger's data with your
  confidence attached.

**Why it generalises.** This is the failure that survives a culture of careful output validation —
so it is most likely to occur precisely where people have already invested in honest reporting. The
more caveats a surface carries, the more authority its number borrows, and the less anyone
re-examines where the number came from. A page that said "context: 8%" with no qualification would
have been doubted sooner than one that said "8% of 1M, session `abc12345`, 3s old".

**The cheap fix, in both directions.** Make the selector state what it selected, next to the value —
the corrected page prints the session id alongside the percentage, which is what makes a
wrong-session reading visible at a glance. And make "found nothing" a distinct, loud outcome rather
than an invitation to fall back.
