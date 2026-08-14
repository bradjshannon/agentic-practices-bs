# A definition is not a status line — locate before you differentiate

**Symptom.** A generated spreadsheet defined one of its columns, `H`, as:

> `H history (calibration, not a factor)`

The operator, reading it cold:

> *"This is supposed to be the DEFINITION of H, for a first time reader. I am a first time reader. I
> have less of an idea of what the fuck H is after reading this, than I did before."*

**What actually happened.** Three successive diagnoses, each better than the last, and only the
third is the real one:

1. *Missing context* — the author knew things the reader does not. **Wrong fix**: adding surrounding
   material would not have helped.
2. *Compression into slogan* — an already-simple idea reduced to something rhetorically neat and
   empty. His words: *"calibrating what? a factor in what? the author believes we've been having a
   conversation, and that i have all this context that does not exist."* Closer.
3. **The definition never places the term in anything the reader already has.** His analogy:

   > *"It's like an alien asking, hey what's soccer, and you say 'foosball, but with real people'"*

   That answer is pure *differentia* offered to someone with no *genus* to differentiate within. It
   never says soccer is a game, played with a ball, by teams — so the new term has nothing to attach
   to, and the words defining it are themselves unknown.

The classical failure has a name: **obscurum per obscurius**, explaining the obscure by the more
obscure. "Calibration" and "factor" were both less established for the reader than `H` itself.

**The compounding cause is a style rule applied out of its domain.** That estate's guidance pushes
hard toward terseness — state the thing, cut the setup, lead with the fact — and for a *status line*
that is correct. A status line addresses someone who already holds the situation, so setup is pure
overhead. **A definition addresses someone with no prior at all, where the setup IS the content.**
The house style did not distinguish the two, so the empty definition was the style working as
designed.

**The rule.** Say what **kind** of thing it is first; refine second; and only refine against
something the entry has already established.

- `H` needed: *how many times this rule has actually been broken, that we have a dated record of.*
  One sentence, locating it as a count of events. Only *then* is "it is deliberately excluded from
  the score" meaningful, because only then does the reader know a score exists.
- **Order matters within a document.** If `score` is defined below `H`, `H`'s entry cannot lean on
  it — order so nothing forward-references, or make each entry self-contained.

**The test: could a reader who knows nothing name the category of thing after the first sentence?**
If that sentence is a contrast, a caveat, or an exception, it fails — all three are differentiation,
and there is nothing yet to differentiate from.

**Why it generalises.** It applies to every artifact where a reader meets a term for the first time:
legends, schema docs, `--help` text, error messages, API field descriptions, code comments naming a
concept, onboarding docs. It also predicts *where* the failure will appear — anywhere a house style
optimised for terse status reporting is applied to explanatory writing, which in a codebase is
usually the generated artifacts nobody re-reads. **Plain and slightly long beats terse and empty.**

Applied as a checklist, this caught two more instances in the same document that its own author had
just written — "Ordinal, not cardinal" and "Partition, not an ordering" — both the identical shape.
