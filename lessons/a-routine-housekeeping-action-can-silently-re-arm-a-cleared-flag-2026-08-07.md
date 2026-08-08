# A routine housekeeping action can silently re-arm a flag someone already cleared

**Symptom.** A dashboard/status card asks a human a question. The human answers. Some time
later — often hours, often via a completely separate, routine action (acknowledging an inbox,
archiving a notification, running a scheduled cleanup) — the card starts asking the same
question again, with no new event that looks like it should have caused that.

**What actually happened.** The "does this need the human's attention" signal was computed from
more than one underlying flag: an *answer-suppression* flag (set when the human replies, so the
card stops nagging) and an *acknowledgement* flag (set when the housekeeping action runs, meaning
"I have seen and filed this reply"). The suppression flag's condition was written as "suppress
while unacknowledged" — i.e. it depended on the ack flag too, on the assumption that acking always
happens *after* the human's reply has been read and acted on. It doesn't: acking is routine,
happens on a fixed cadence, and has no way to know whether the reply it's acking actually settled
the question. The moment a run acks a reply without also resolving what the reply was about, the
suppression condition flips back to "unanswered," and the badge reappears — indistinguishable from
the card never having been answered at all.

Measured directly: on one board, every single card currently badged "needs a response" was one
the human had already responded to. Not most — all of them. The badge had stopped meaning
"unanswered" and started meaning "answered, but subsequently acked" — a completely different, and
much less useful, signal, wearing the same label.

**A second version of the same class, same session, opposite direction.** The tool built to
*discharge* a stuck "needs a response" badge had two settling actions with different meanings —
one meant "this is finished," the other meant "this stopped being a question for the human and
became my own todo." Both looked like reasonable ways to make a badge go away. Picking the wrong
one didn't clear the signal, it repointed it: the card stopped asking the human and started
claiming to be active work the AGENT owed, which then failed to clear on its own for hours because
nothing else was watching for *that* state either.

**The rule.** Whenever a status flag is derived from a UNION or an AND of several sub-signals set
by different actors at different times, ask specifically: *does any later, unrelated, routine
action have the power to flip this signal back, without knowing that's what it's doing?* Routine
actions (ack, archive, sweep, cleanup) are exactly the ones that run unconditionally and don't
carry the semantic context a *deliberate* resolution would. If a routine action can move a
user-facing signal, either (a) make the routine action's effect on that signal a no-op — acking a
message should never itself change whether a linked decision counts as answered — or (b) give the
routine action the context it needs to know whether the signal should actually move.

**The cheap partial mitigation, if the full fix isn't worth it yet:** make the two meanings of a
shared verb/flag textually explicit at the point of use, not just in a docstring nobody reads
before typing the command. A CLI flag named for its mechanism ("clear this flag") rather than its
intent ("stop asking" vs "make this my todo") is a trap the author of the mechanism itself walked
into, live, using their own tool.
