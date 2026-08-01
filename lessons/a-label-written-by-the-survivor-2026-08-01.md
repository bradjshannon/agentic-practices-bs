# A label written by the survivor, about the casualty

**Symptom.** A crash report carried a version string identifying which build had crashed. Twice,
that string pointed at a binary that had demonstrably not been running when the crash occurred.
The first time it cost a whole diagnosis — a search of 103 candidate binaries for one that did not
exist, and a conclusion that the crash was permanently unanalysable. The second time it was caught
only because the same investigator had been burned an hour earlier and thought to check.

**What actually happened.** The field was populated at *upload* time, not at *crash* time. That was
deliberate and documented: crash dumps are stored in flash and survive reboots, so the uploader
runs later — sometimes several boots later — and stamps the record with whatever is running when
it finally gets a network connection.

Under normal conditions that is harmless: the process that crashed is the process that reboots and
uploads, so the label is correct. It becomes a lie under exactly one condition — when something
*replaces* the binary between the crash and the upload. In this system that condition was a
software update: the crash landed in the window between "new image committed to flash" and "reboot
into it completes", so the device came back as the *new* build and labelled the *old* build's dump
with the new build's name.

That is not a rare corner. It is the single most interesting moment in the system's life, and the
one you most want a crash report from.

**The rule.** When a diagnostic field is derived at a different time from the event it describes,
enumerate what can change in between — and check whether the interesting failures live precisely
in that gap. They usually do, because the gap is where state is in motion, and state in motion is
what breaks.

Then prefer a field the artifact carries *itself* over one an observer attaches later. Here the
dump embedded its own content hash of the binary that produced it, and the lookup path already
keyed on that hash. The human-readable label was a convenience that disagreed with the
authoritative field, and every consumer trusted the convenience.

**Why it generalises.** This is a class, not an incident. Anything stamped by a survivor about a
casualty has it: a log line timestamped at flush rather than at emit; an error tagged with the
config loaded now rather than the config that was loaded when it failed; a build annotated with
the branch checked out at packaging time; a metric labelled with the schema version current at
scrape. In each case the label is right on every ordinary day and wrong on the day you need it.

**Two things that make it hard to catch:**

- **The field is usually right**, so it accrues trust. There is no accumulating error to notice —
  just a rare, total inversion.
- **It fails silently and plausibly.** A wrong-but-well-formed label sends you looking for
  something real, and the search fails in a way that looks like *your* problem, not the label's.
  The first investigator concluded the artifact was lost. The artifact was never lost; the pointer
  was wrong.

**The cheap check, when you next distrust a record:** ask what the record knows about *itself*
versus what was attached to it, and compare the two. A disagreement between a self-describing field
and an attached one is not ambiguity — the self-describing field wins, and the disagreement is
itself the finding.
