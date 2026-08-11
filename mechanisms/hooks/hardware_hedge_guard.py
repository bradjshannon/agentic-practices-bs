#!/usr/bin/env python3
"""Stop hook: do not tag a PHYSICAL hardware fact "unverified" without consulting an authority.

WHY THIS HOOK EXISTS
--------------------
Twice in one session (2026-07-30) the conductor marked a settled hardware fact as unverified,
and both times the answer was already in hand:

  * "whether the two ES7210 M-slots are two physically distinct PCB mics ... is a hardware fact
    I can't settle from code" -- about a mass-produced board sitting on the desk, with a
    published datasheet, brought up from scratch on this bench with each mic tested
    individually, and ~2 weeks of the wakeword working. The operator: *"or the board sitting in front of
    me, which has two mics on the pcba, and is a known, established, mass produced product on
    the market, with like specs and datasheets ???"* / *"we brought up this board from scratch
    and tested each mic ?!?!"*
  * "OMOBE's mic is unverified ... I can't currently confirm OMOBE captures audio at all" --
    about an audio dev board that had been running voice turns and producing transcripts. The operator:
    *"what? are you crazy"*. That one was internally incoherent too: the same sentence noted
    that `mic_dbfs` reads floor on a WORKING mic, then used the floor reading to doubt the mic.

The root error is not laziness. It is applying source-code skepticism to a physical fact:
reasoning from "no agent has re-derived this from source recently" to "this is open." **Absence
of a re-derivation is not evidence of doubt.** Three authorities were available and unconsulted
each time -- the vendor datasheet, the operating history, and the bring-up record.

WHY PROSE DID NOT WORK, MEASURED
--------------------------------
A hardware-facts register (`conductor-bs/conductors/myproject/hardware-facts.md`) was written at
~02:00 with exactly this rule, and named in PRIMING.md so every run indexes it. **The second
instance happened at ~03:00, by the same agent that wrote the register.** That is the
Voluntary-class decay this project's own enforcement table predicts, arriving inside one
session. A rule that fails twice moves up a class rather than getting rewritten again.

WHAT IT DOES
------------
On Stop, for the current turn: if the agent's own text hedges about a PHYSICAL hardware fact,
and the turn shows no sign of having consulted an authority, block once and name the three
authorities.

THE COUPLING, AND ITS HONEST LIMIT
----------------------------------
Unlike `evidence_with_claim`, this hook CANNOT verify that the authority was consulted well --
only that something authority-shaped appears in the turn (a Notion fetch, a datasheet path, a
read of the register). So it raises the floor rather than solving the problem: it makes the
UNVERIFIED tag cost one lookup. That is the whole intent. It also cannot fire on an assumption
the author does not know they are making, which is the failure mode that produced instance one.

SCOPE GUARDS -- each is a false positive that would discredit the hook
  * Only PHYSICAL nouns (mic, PCBA, GPIO, pin, solder, ADC, codec, a part number). NOT software
    words. "the wire contract is unverified" must not fire.
  * The hedge and the hardware noun must be in the SAME SENTENCE. Proximity is the whole signal;
    a turn that hedges about one thing and mentions a mic elsewhere is not this defect.
  * Blockquoted lines are ignored -- that is the operator or a doc speaking, not the agent asserting.
  * A turn that ASKS rather than asserts is ignored (the sentence ends in `?`). Asking is the
    behaviour this hook wants to produce.
  * Only fires when the turn made >=1 tool call, matching evidence_with_claim: taxing a pure
    conversation turn trains the escape token into a standing header, which is the measured
    decay signature in every other hook here.

OVERRIDE
--------
`hardware:unverified-ok` proceeds -- for the legitimate case, e.g. a genuinely novel board with
no datasheet, or a fact that really does need a meter. Both shapes are logged (`overridden` on a
turn that would have blocked, `preemptive` on one that would not), because an override rate that
climbs is the signal that this hook has become a formality.
"""
import json
import os
import re
import sys

OVERRIDE = re.compile(r"hardware:\s*unverified-ok\b", re.I)

# --- the hedge, i.e. the shape being policed ---------------------------------------------
# Deliberately only the ABSOLUTE forms. "not yet measured on this board" is honest and useful;
# "cannot be established" about a mass-produced part is the defect.
_HEDGE = re.compile(
    r"\bUNVERIFIED\b"
    r"|\bunverified\b"
    r"|\bnot verified\b"
    r"|\bnot established\b"
    r"|\bcan(?:'t|not) (?:confirm|settle|establish|determine|tell|know|verify)\b"
    r"|\bunable to (?:confirm|settle|establish|determine|verify)\b"
    r"|\bno way to (?:know|tell|confirm|verify)\b"
    r"|\bunknown whether\b"
    r"|\bnobody (?:has )?(?:read|checked|verified)\b",
    re.I,
)

# --- PHYSICAL hardware nouns only --------------------------------------------------------
# A software noun here would make the hook fire on ordinary honest hedging about code, which is
# the behaviour the OTHER hooks exist to encourage. Keep this list physical.
_HARDWARE = re.compile(
    r"\bmic(?:s|rophone|rophones)?\b"
    r"|\bPCBA?\b"
    r"|\bGPIO\b|\bpin(?:s|out)?\b|\bstrapping\b"
    r"|\bsolder(?:ed|ing)?\b|\bDNP\b|\brework\b"
    r"|\bADC\b|\bDAC\b|\bcodec\b|\bexpander\b|\bamp(?:lifier)?\b|\bspeaker\b"
    r"|\bschematic\b|\bdatasheet\b|\bpart number\b|\bSKU\b"
    r"|\bresistor\b|\bcapacitor\b|\bdivider\b|\bdiode\b|\bcrystal\b|\boscillator\b"
    r"|\bheader\b|\bconnector\b|\bcastellat\w*\b|\btrace\b"
    r"|\bES7210\b|\bES8311\b|\bTCA9555\b|\bMCP23017\b|\bNS4(?:150|168)\w*\b"
    r"|\bAXS15231\b|\bBAT54\w*\b|\bMAX3232\b|\bSN74HC245\b",
    re.I,
)

# Signs the turn actually consulted an authority. Matched against this turn's TOOL RESULTS, not
# against what the agent said about them -- a claim of having looked is not a look.
_AUTHORITY = re.compile(
    r"notion"                     # a Notion fetch/search result
    r"|hardware-facts\.md"        # the register
    r"|datasheet|Specification|user[_ ]manual"
    r"|device-roster\.md"
    r"|bsp_\w+\.h"                # a board support header
    r"|sdkconfig",
    re.I,
)


def strip_blockquotes(text: str) -> str:
    """Drop quoted lines -- the operator or a doc speaking, not the agent asserting."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))


def sentences(text: str) -> list[str]:
    """Crude sentence split. Good enough: the signal is same-sentence proximity, and a split
    that occasionally merges two sentences errs toward NOT firing."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}|\n[-*]\s+", text) if s.strip()]


def find_hedges(said: str) -> list[str]:
    """Sentences that hedge about a physical hardware fact. [] when clean."""
    out = []
    for s in sentences(strip_blockquotes(said)):
        if s.rstrip().endswith("?"):
            continue  # asking is the desired behaviour, not the policed one
        if _HEDGE.search(s) and _HARDWARE.search(s):
            out.append(" ".join(s.split())[:220])
    return out


def evaluate(said: str, results: str, calls: int) -> tuple[bool, list[str]]:
    """(would_block, offending_sentences). Pure, so tests drive it without a transcript."""
    if calls < 1:
        return False, []
    hedges = find_hedges(said)
    if not hedges:
        return False, []
    if _AUTHORITY.search(results or ""):
        return False, hedges   # an authority was consulted; the hedge is then informed
    return True, hedges


def turn(transcript_path: str) -> tuple[str, str, int]:
    """Shared turn window. Fails OPEN -- a broken instrument must not block the session."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from turn_window import turn as _shared
        t = _shared(transcript_path)
        return t["said"], t["tool_results"], t["tool_calls"]
    except Exception:
        return "", "", 0


def _log(event: str, trigger: str, transcript: str, extra: dict) -> None:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("hardware_hedge_guard", trigger=trigger,
                        transcript_path=transcript, extra=dict(extra, event=event))
    except Exception:
        pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("stop_hook_active"):
        return 0

    transcript = payload.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        return 0

    said, results, calls = turn(transcript)
    would_block, hedges = evaluate(said, results, calls)
    overridden = bool(OVERRIDE.search(said))

    if overridden:
        _log("overridden" if would_block else "preemptive",
             hedges[0] if hedges else "(no hedge detected)", transcript,
             {"hedges": len(hedges)})
        return 0

    if not would_block:
        return 0

    shown = "\n".join(f"  ...{h}..." for h in hedges[:3])
    reason = (
        "This turn tags a PHYSICAL hardware fact as unverified, and nothing in the turn shows "
        "an authority was consulted:\n\n" + shown + "\n\n"
        "These boards are MASS-PRODUCED PRODUCTS. They have published datasheets, they were "
        "brought up from scratch on this bench with each peripheral tested individually, and "
        "they have weeks of operating history. Absence of a re-derivation is NOT evidence of "
        "doubt -- and an UNVERIFIED tag reads to the operator as a real open question, costing them a "
        "round-trip to close something he already knows.\n\n"
        "Three authorities are owed before the tag, in order:\n"
        "  1. Is it a mass-produced product? Fetch the vendor datasheet / product page. Having "
        "read only the firmware source is a choice of one source, not a limit.\n"
        "  2. Has the system been DOING the thing? Working behaviour is evidence about "
        "hardware. Operating history is data.\n"
        "  3. Was it established at bring-up? Ask, or find the record.\n\n"
        "Authority order: Notion \"Hardware Reference\" pages (search the Notion MCP) > vendor "
        "datasheet > bring-up history and observed behaviour > board BSP/Kconfig (authoritative "
        "for SOFTWARE only) > repo docs/*.md snapshots > your recollection, which is not a "
        "source. Register: conductor-bs/conductors/myproject/hardware-facts.md\n\n"
        "FIX: consult one of them and say \"established, per <source>\", or ASK the operator in one "
        "line. Both are cheap. If the fact genuinely needs a meter or the board is genuinely "
        "undocumented, emit `hardware:unverified-ok` -- override use is LOGGED, including "
        "pre-emptive use, so decay is visible.\n\n"
        "Measured: this happened TWICE on 2026-07-30, the second time one hour after the same "
        "agent wrote the register that forbids it. That is why this is a hook and not a "
        "paragraph."
    )
    _log("fire", hedges[0], transcript, {"hedges": len(hedges)})
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
