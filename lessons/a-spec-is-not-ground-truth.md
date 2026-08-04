# A spec is not ground truth

**Symptom.** I graded a model's behaviour against its own system prompt and reported it as a
defect: the model set a heater to 80°F while the prompt said the valid range was "140 to 200". I
filed it INCORRECT, twice, with the prompt quoted as the authority.

**What actually happened.** The prompt was wrong. 140–200°F is an air-fryer *cooking* range that
had been copy-pasted into a *room fan* agent, along with its burn warnings. 80°F is a correct
room-air target, and the device accepted it — which was in my own evidence the whole time. The
model was right and the specification was the defect. The human caught it; my self-checks could
not have, because every check I ran validated against the same bad document.

**The rule.** When behaviour contradicts its specification, the specification is a *suspect*, not a
*referee*. Before filing the behaviour as wrong, ask what would be true if the spec were wrong
instead — and look for the independent signal (here: the device accepted the value). This is the
same failure as trusting a green check: a document, like a status endpoint, is a claim about the
system, not a measurement of it.

**Why it generalises.** Specs, prompts, schemas, config and docs are all written earlier than the
code and maintained worse. Any agent that grades an implementation against a written artifact
inherits that artifact's errors and launders them as findings — with more confidence than the
artifact ever deserved, because quoting it *feels* like evidence. Cheap tell: the spec is generic
boilerplate, or mentions a different product than the one you are looking at.
