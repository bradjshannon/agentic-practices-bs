#!/usr/bin/env python3
"""Stop hook: chat output has a per-turn character budget; over-budget must be justified.

WHY THIS IS A HOOK AND NOT A NOTE
---------------------------------
An output-efficiency review of one real session measured the problem precisely: the agent
emitted ~132,000 characters of prose against ~5,400 from the human (a 24.6:1 ratio); ~55% of a
sampled slice was reasoning and process-narration the human never asked for; 23 of 49 "what do
you need" lines said "nothing"; and -- the decisive number -- after the human explicitly asked
for less, output volume went UP: the final quarter of the session averaged 20% longer messages
than the first.

That last fact is the whole argument. "Be concise" is a rule the agent already had, agreed to,
and then violated while agreeing. A prose rule for output length is the voluntary class: it is
satisfiable by *saying* you will be brief, and it decays under exactly the pressure that makes
brevity matter. So the control has to fire without the agent's participation and has to be
measured, not felt -- the agent cannot perceive its own accumulated length any more than it can
feel elapsed time.

WHAT IT DOES
------------
On Stop, sum the characters of the assistant's own TEXT this turn (tool calls and their results
don't count -- this is about what the human has to READ). If it exceeds the budget and the turn
carries no justification token, block once with the number and the five-line default shape.

The budget is deliberately generous: this is a backstop against walls, not a gag. A turn that
genuinely needs length -- a decision with its full reasoning, an answer the human asked to be
thorough -- says so with a one-word token and proceeds. The token is a speed bump, not a wall:
its cost is that the agent has to NAME why this turn is long, which is exactly the reflection the
review found absent.

Justification tokens (any one, anywhere in the turn's text):
  output-budget:ok        -- generic: this length is warranted, I have considered it
  output-budget:asked     -- the human asked for depth / a long answer this turn
  output-budget:artifact  -- the length is a deliverable being shown inline (a table, a spec)

WHY A CHARACTER BUDGET AND NOT A LINE COUNT
-------------------------------------------
Lines hide length -- one 3,000-char paragraph is one line. Characters are what the human's eye
actually pays. The review's own unit was characters; this uses the same one so the budget can be
tuned against measured data rather than guesswork.

CALIBRATION
-----------
BUDGET is set to 2,200 chars ~= 350 words ~= a comfortable phone screen. The review's median
message was 285 chars and its *mean* 505; 2,200 sits well above both, so an ordinary status turn
never trips it. What trips it is the 1,000+-char message: 48 of those carried 55% of the entire
session's reading load from 18% of the messages. This targets that tail specifically.
"""
import json
import os
import re
import sys

BUDGET = 2200
# A question buys MORE room, not unlimited room -- see the exemption below for what the
# unlimited version cost. 2x is enough for a real answer with its reasoning and still fits a
# couple of phone screens.
QUESTION_BUDGET = BUDGET * 2

OVERRIDE = re.compile(r"output-budget:\s*(ok|asked|artifact)\b", re.I)


# A turn that ANSWERS a direct question is exempt. Brad, 2026-07-22: "the output budget hook
# needs to ignore ... instances of overriding it when i ask you questions. it was meant to
# address the problem of returning to a session and having an hour of reading."
# The target is UNPROMPTED volume -- status dumps, narration, the wall you come back to. An
# answer to a question the human just asked is not that; taxing it trains truncated answers and,
# worse, poisons the measurement: every question-answer was logging a fire/override, so the
# hook's own effectiveness data (hook_log -> hook_rollup) counted legitimate answers as
# violations. Kept deliberately CONSERVATIVE -- a "?" or a short list of ask-shaped openers --
# because an over-broad exemption silently guts the hook, which is the failure mode that matters.
# Deliberately NARROW. An earlier draft included bare auxiliaries ("do ", "is ", "can ", "any ")
# and the test suite immediately caught it: "do the thing" is an INSTRUCTION, not a question, and
# exempting it would have quietly gutted the hook on ordinary work turns. Only a literal "?" or an
# explicit request-for-exposition verb counts.
_ASK_OPENERS = ("explain", "tell me", "describe", "summarize", "walk me through")


def is_question(human_text: str) -> bool:
    """Did the human ASK something? Conservative on purpose (see comment above)."""
    t = (human_text or "").strip().lower()
    if not t:
        return False
    if "?" in t:
        return True
    return t.startswith(_ASK_OPENERS)


def current_turn_text(transcript_path: str) -> tuple[str, str]:
    """(assistant text this turn, the human message that started it).

    A user entry with STRING content is real human input; a list-shaped one is a
    tool result being fed back, which does not reset the budget -- otherwise a
    chatty turn full of tool calls would keep resetting its own counter.
    """
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
    except Exception:
        return "", ""

    start = 0
    human = ""
    for i in range(len(entries) - 1, -1, -1):
        e = entries[i]
        if e.get("type") != "user":
            continue
        content = (e.get("message") or {}).get("content")
        if isinstance(content, str) and content.strip():
            start = i
            human = content
            break
        # A human message WITH ATTACHMENTS (screenshots, pasted files) is list-shaped, exactly
        # like a tool result — so the original string-only scan skipped it, walked further back
        # to an older message, and the question-exemption never saw the question. Observed
        # 2026-07-22: Brad asked "what does this mean?" with two screenshots attached and the
        # budget hook fired on the answer, which is the precise case the exemption exists for.
        #
        # The discriminator is the BLOCK TYPES, not the container: real human input carries
        # `text` blocks, a tool result carries `tool_result`. Checking the shape of the content
        # rather than the shape of the wrapper is what makes this correct rather than lucky.
        if isinstance(content, list):
            kinds = {b.get("type") for b in content if isinstance(b, dict)}
            if "tool_result" in kinds:
                continue  # genuinely a tool result feeding back — does not reset the budget
            said = "\n".join(b.get("text") or "" for b in content
                             if isinstance(b, dict) and b.get("type") == "text")
            if said.strip():
                start = i
                human = said
                break

    parts = []
    for e in entries[start:]:
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
    return "\n".join(parts), human


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never break the session on a malformed payload

    if payload.get("stop_hook_active"):
        return 0

    transcript = payload.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        return 0

    text, _stale_human = current_turn_text(transcript)
    n = len(text)

    # TWO DIFFERENT WINDOWS, deliberately — this is a decision, not an oversight.
    #
    # MEASURE per message (the notification-bounded window above). Brad reads a message at a
    # time, and a per-message cap is what keeps any single one skimmable.
    #
    # EXEMPT on the real human boundary. `current_turn_text` treats a background-task
    # notification as human input — measured: 25 notifications vs 37 genuine messages in one
    # session — so the question-exemption was inspecting a notification instead of Brad's actual
    # question, and fired on the answer to "what does this mean?".
    #
    # Not switching the MEASUREMENT to the human boundary too, though it is tempting: cumulative
    # output since he last spoke was 14,511 chars in one stretch here, so a 2,200 cap on that
    # window would block every turn and become a token-typing ritual. The cumulative number is
    # the more honest measure of his reading load and is worth surfacing, but a control that
    # fires constantly is one that gets routed around -- the exact decay this file documents.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from turn_window import turn as _real_turn
        human = _real_turn(transcript)["human"]
    except Exception:
        human = _stale_human  # fail toward the old behaviour rather than losing the exemption

    if n <= BUDGET or OVERRIDE.search(text):
        return 0

    # Answering a direct question RAISES the budget; it does not remove it.
    #
    # 2026-07-26: this exemption was `if is_question(human): return 0` -- unlimited length. It
    # ate the entire control. Brad asks a question in most messages ("mechanical fix options?",
    # "do i want them directly next to the OLED?", "are reassert failures a class of error?"),
    # so the cap never applied ONCE across a long session, and he ended up saying: "i'm already
    # regressing to reading through pages and pages of your output in chat. can't do it, not
    # sustainable, it's handcrafting instead of automating."
    #
    # He was describing this file failing. The bug is the shape of the exemption, not its
    # existence: "he asked something substantive" is a real reason for MORE room and never a
    # reason for INFINITE room. A binary exemption on a condition that is usually true is
    # indistinguishable from having no control.
    if is_question(human) and n <= QUESTION_BUDGET:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import hook_log
            hook_log.record("output_budget",
                            trigger=f"{n} chars EXEMPT (question, under {QUESTION_BUDGET})",
                            transcript_path=transcript, extra={"exempt": "question"})
        except Exception:
            pass
        return 0

    reason = (
        f"This turn emitted {n:,} characters of chat text (budget {BUDGET:,}). A measured "
        "session showed output volume RISING 20% right after the human asked for less -- 'be "
        "concise' is the rule that decays while being agreed to, which is why this is a hook.\n\n"
        "Default shape, ~5 lines:\n"
        "  Changed: <what changed>\n"
        "  Needs you: <a decision, or 'nothing'>\n"
        "  Next: <what's next>\n"
        "Reasoning, derivations and status detail go in the commit or a repo doc, where they are "
        "greppable -- not in chat, which the human reads serially and hours behind.\n\n"
        "If this length is warranted, say so and proceed:\n"
        "  output-budget:asked     -- the human asked for depth this turn\n"
        "  output-budget:artifact  -- the length IS a deliverable shown inline\n"
        "  output-budget:ok        -- warranted for another reason (name it)\n\n"
        "The token is a speed bump: its whole cost is naming why this turn is long."
    )
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("output_budget", trigger=f"{n} chars (budget {BUDGET})",
                        transcript_path=transcript, extra={"mode": "advisory"})
    except Exception:
        pass

    # ADVISORY, NOT BLOCKING (Brad, 2026-07-24: "you're repeating yourself in this chat").
    #
    # This hook blocked until now. Blocking a Stop forces the agent to REWRITE the message --
    # but the over-long original has already been shown to Brad, so he reads the whole thing
    # twice. A guard whose entire purpose is reducing what he reads was, every time it fired,
    # roughly DOUBLING it. It fired repeatedly in one session before he noticed and asked why
    # the chat was repeating itself.
    #
    # That is the "false positives cost more than misses" rule in its sharpest form: the harm
    # was not a wrong verdict (the messages really were over budget) but the REMEDY. The block
    # made the problem worse in exactly the case it was designed to catch.
    #
    # So it now records and stays silent. The signal is still measurable in the hook log --
    # `mode: advisory` marks fires from this point, so the rate can be compared against the
    # blocking era rather than assumed unchanged. If volume climbs without the block, that is
    # an argument for a different mechanism (one that acts BEFORE the message is emitted, which
    # a Stop hook structurally cannot), not for restoring a remedy that costs double.
    return 0


if __name__ == "__main__":
    sys.exit(main())
