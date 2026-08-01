# "Absent from the place I looked" is not "absent"

**Symptom.** A firmware crash on an ESP32 board could not be symbolicated. The build's ELF was
not in the symbol store, so the agent — and then the conductor, and then a report to the human —
declared the coredump *permanently undecodable*, and reasoned onward from that: what the
diagnostics gap cost, which mechanism to fix, what to card. The claim was repeated three times
in escalating confidence before anyone tested it.

**What actually happened.** A sweep of 103 ELF files on the machine found it immediately, in an
OTA build directory nobody had thought to look in. The negative had been derived from exactly
one `ls` against exactly one directory — the directory the archiving tool *writes* to. That is a
statement about the archiver, not about the filesystem.

Worse, the search that finally ran also produced the *real* answer, which was different again:
the recovered ELF turned out not to match the dump either. The binary that crashed had a
different hash, because two builds off the same dirty working tree minutes apart share an
identical version string. So the first conclusion ("no ELF exists") was wrong, the second
("here is the ELF") was wrong, and only the third — reached by hashing everything and running a
positive control — held.

**The rule.** A negative-existence claim is only as strong as the *breadth* of the search that
produced it, and that breadth must be stated with the claim. "Not in the symbol store" and
"does not exist" differ by every directory you did not enumerate. Before acting on an absence:

1. Say where you looked, in the claim itself. If you cannot name the roots, you do not have a
   negative — you have an unsuccessful lookup.
2. Ask what *else* would hold the thing if the expected mechanism had failed. The expected
   mechanism failing is precisely the situation you are in.
3. Run a **positive control** over the same search: point the method at something you know is
   present and confirm it finds it. An empty result from a broken instrument looks identical to
   an empty result from an empty world.
4. Prefer content addressing to path addressing. Hashing every candidate answers "does this
   exist anywhere" in a way that checking a canonical location never can.

**Why it generalises.** This is the same shape as an instrument's silence being read as data,
but with a twist that makes it easier to fall for: the lookup *succeeded*. There was no error,
no timeout, no empty log to be suspicious of — `ls` correctly reported that a file was not in a
directory, and that true statement was silently widened into a false one. Nothing in the tooling
could have flagged it, because nothing was wrong with the tooling.

The cost here was cheap only by luck: the wrong conclusion drove a report to the human and a
choice of which defect to fix first. In a search-and-prune context it is expensive by
construction — a false negative permanently removes a branch from the search, and nothing ever
revisits it.

**The tell to watch for in your own output:** you wrote "X does not exist" but what you ran
answers "X is not at P". If the sentence would still be true with a location clause attached,
attach it and see whether the conclusion still follows. Usually it does not.
