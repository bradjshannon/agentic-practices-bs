# skills

Agent **skills** — a directory holding a `SKILL.md` plus whatever it invokes — as opposed to the
event-fired scripts in [`../hooks/`](../hooks). Same rules as the rest of `mechanisms/`: this is
a catalogue, nothing here executes from this repo, and an entry's presence here is **not**
evidence it is wired up on your machine.

A skill differs from a hook in one way that matters for adoption: a hook is inert until it is
attached to an event, whereas a skill is inert until an agent *decides* to invoke it. That makes
a bare skill the **Voluntary** class by construction, however good the code inside it is. So a
skill banked here should ship with — or explicitly decline to ship — a trigger that moves it up
the ranking in [`../README.md`](../README.md).

| Path | What it does |
|---|---|
| [`freshness-check/`](freshness-check/README.md) | A staleness registry for load-bearing doc claims nothing else watches: entries carry a `last_checked` date and a cadence, and a script does deterministic date math to report what is due. Ships an **example** SessionStart trigger, because the skill alone is Voluntary and was observed decaying exactly as that predicts (19 entries, zero sweeps). |
