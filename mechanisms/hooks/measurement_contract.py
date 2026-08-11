#!/usr/bin/env python3
"""Measurements that carry their own comparability contract. (portable; see mechanisms README)

THE PROBLEM THIS EXISTS FOR. A bare integer looks comparable to another bare integer. Twice in
one day on one project (myproject, 2026-08-01) two numbers were subtracted that had no business being
subtracted -- the incidents are concrete but the failure is not domain-specific:

  - "enabling WakeNet FREED 22,640 B" -- two readings differing in wake-state AND uptime AND
    session activity. Controlled, the sign INVERTED: wakeword costs ~16.9 KB.
  - An ADR's host-headroom gate compared 2,863 B (board "live") against 19,075 B (board idle)
    and attributed the gap to four commits, none of which could have caused it.

Both were written by people being careful. Neither number carried what would make a later number
comparable to it, so nothing could object.

THE DESIGN, and the part that matters is WHEN. The contract is stated at STORE time, by the author,
who is the only one who still knows what they controlled. It is not inferred later and not
enumerated up front by whoever designs the schema -- they do not know which conditions mattered for
your reading.

    m = Measurement(
        metric="internal.free", value=26679,
        instrument="get_memory_report",          # cap masks differ per tool; see below
        subject="esp32-s3-rgb-matrix-cbda9c",
        conditions={"build": "e89b0c5", "uptime_s": 324,
                    "session_active": False, "wake_enabled": 1, "afe_active": True},
        comparable_when=["build", "uptime_s~60", "session_active", "wake_enabled"],
    )

`comparable_when` IS the checker. There is no separate hand-written comparison rule to drift from
it: `compare()` reads the field. A key you forgot is not an omission someone has to notice, it is a
mismatch the tool reports.

FOUR DECISIONS THAT ARE NOT ARBITRARY:

1. **The UNION of both contracts must hold, not the intersection.** A comparison is valid only if
   BOTH authors would have accepted it. Intersection would let one lazy record erode a careful one --
   which is precisely how a casual reading pasted into a doc poisons a rigorous one.

2. **`instrument` and `subject` always match, whatever the contract says.** Not negotiable, because
   this is the failure that hides best: `get_memory_report.internal.*` uses
   `MALLOC_CAP_8BIT|INTERNAL` and `get_device_status.idram_*` uses `8BIT|DMA|INTERNAL`. Measured
   minutes apart on one healthy board: 2,475 B vs 8,491 B. That difference looks exactly like a
   memory collapse and has manufactured a false conclusion here in BOTH directions.

3. **It refuses; it does not warn.** A warning you can ignore is not a control -- this codebase's own
   doctrine. `compare()` returns a verdict you must read, and `require_comparable()` raises.

4. **An explicit independent variable.** `compare(a, b, varying="wake_enabled")` exempts exactly one
   key and demands everything else hold. Naming what you are varying is the whole experiment; if you
   cannot name it, you are not running one.

THE CEILING, stated so nobody oversells it. This forces the contract to EXIST, not to be RIGHT.
`comparable_when=["build"]` on a reading whose value actually depends on uptime will happily compare
two incomparable things. That is the same ceiling `evidence_with_claim` has. It is still a strict
improvement: a wrong contract is visible and falsifiable, whereas the absent contract that caused
both failures above was invisible. And being made to write "comparable to anything on this board"
tends to make you notice you are claiming something strong.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

#: A doc cites a measurement by id; it does not restate the conditions. `cite()` emits this.
CITE = re.compile(r"\[m:([0-9a-f]{6,64})\]")

_TOL = re.compile(r"^(?P<key>[A-Za-z0-9_.]+)~(?P<tol>\d+(?:\.\d+)?)$")

#: Always compared, regardless of what a contract says. See decision 2 in the module docstring.
MANDATORY = ("instrument", "subject")


class ContractError(ValueError):
    """The measurement is not storable: its contract is missing or does not describe it."""


class Incomparable(ValueError):
    """The two measurements may not be compared. Carries every reason, not just the first."""


#: Confounders this project has LEARNED matter, per (metric-ish, instrument) scope. It GROWS.
#: Each entry is the date it was learned; a measurement records the entries known at store time.
#: This is the mechanism for "we cannot enumerate every confounder pre-emptively" -- you do not
#: need foresight, you need discovery to propagate BACKWARDS onto readings already taken.
KNOWN_CONFOUNDERS: dict[str, str] = {}


def set_registry(confounders: dict[str, str]) -> None:
    """Install this project's known-confounder registry: {condition_name: date_learned}.

    THIS DICT IS THE ONLY PROJECT-SPECIFIC PART OF THE MODEL. Everything else -- the
    store-time contract, the union rule, the three verdict states, retroactive demotion,
    the citation chain -- is domain-independent. If a project cannot express its confounders
    as entries here, the abstraction is wrong and that is worth knowing quickly.

    It is meant to GROW. Adding an entry retroactively demotes every stored measurement that
    did not record that condition, which is the whole point: you cannot enumerate confounders
    in advance, but you can make discovery reach backwards.
    """
    KNOWN_CONFOUNDERS.clear()
    KNOWN_CONFOUNDERS.update(confounders)


def load_registry(path) -> None:
    """Install a registry from a JSON file: {"uptime_s": "2026-08-01", ...}."""
    with open(path, encoding="utf-8") as fh:
        set_registry(json.load(fh))


@dataclass(frozen=True)
class Verdict:
    """Three states, because "not refused" is NOT "valid".

    `comparable_when` states NECESSARY conditions. Treating them as SUFFICIENT is an unbounded
    claim -- it asserts that every confounder was enumerated, which nobody can do. So the
    positive verdict deliberately does not say "comparable"; it says no known objection, and
    lists what was actually checked, so a reader can see the bound rather than infer none.
    """
    comparable: bool
    reasons: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    checked: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        # An unknown does not refuse -- it withholds. Callers that must not proceed on an
        # unknown use require_comparable(..., strict=True).
        return self.comparable

    @property
    def state(self) -> str:
        if not self.comparable:
            return "REFUSED"
        return "UNKNOWN" if self.unknowns else "NO-KNOWN-OBJECTION"

    def __str__(self) -> str:
        if not self.comparable:
            return "REFUSED: " + "; ".join(self.reasons)
        checked = ", ".join(self.checked) or "nothing"
        if self.unknowns:
            return ("UNKNOWN -- no objection among [" + checked + "], but: "
                    + "; ".join(self.unknowns))
        return f"NO KNOWN OBJECTION (checked: {checked}). Not a claim that nothing else differs."


@dataclass
class Measurement:
    metric: str
    value: Any
    instrument: str
    subject: str
    conditions: dict[str, Any] = field(default_factory=dict)
    comparable_when: list[str] = field(default_factory=list)
    #: Confounders you KNOW matter and know you did NOT control. A declared defect, which is a
    #: different thing from an unknown -- it is knowledge, and it must travel with the reading
    #: rather than living in someone's memory of how the reading was taken.
    known_confounded_by: list[str] = field(default_factory=list)
    #: What the project knew about confounders when this was stored. Left empty and filled in
    #: at construction, so a reading taken before a confounder was discovered is identifiable
    #: as such later instead of silently looking clean.
    confounders_known_at_store: list[str] = field(default_factory=list)
    taken_at: str | None = None
    note: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        if not self.confounders_known_at_store:
            self.confounders_known_at_store = sorted(KNOWN_CONFOUNDERS)
        if not self.id:
            self.id = self._derive_id()
        self.validate()

    def _derive_id(self) -> str:
        """Content-derived, so the same reading gets the same id and a doctored one does not."""
        payload = json.dumps(
            {"metric": self.metric, "value": self.value, "instrument": self.instrument,
             "subject": self.subject, "conditions": self.conditions,
             "taken_at": self.taken_at},
            sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    def cite(self) -> str:
        """The token to paste into a doc alongside the number.

        A prose citation chain is enough -- the operator, 2026-08-01: "as long as there is a chain that
        leads back to the primary source, this may be acceptable. like, once cited, we don't need
        to repeat the citation every time we mention a data point from it."

        So a doc does NOT restate the conditions. It carries this token once, and every later
        mention of the number refers to it. That keeps the contract resolvable without turning
        every sentence into a table -- and it is what makes a stale doc number CHECKABLE rather
        than merely suspect: resolve the id, re-run compare(), see whether the comparison the
        prose is making was ever licensed.
        """
        return f"[m:{self.id}]"

    # -- store-time gate -------------------------------------------------------------------
    def validate(self) -> None:
        """Refuse to exist without a usable contract. This is the whole mechanism.

        Checked at construction, so there is no path that stores a measurement lacking one --
        including the paste-into-a-doc path, if the doc value came from here.
        """
        for f in ("metric", "instrument", "subject"):
            if not str(getattr(self, f) or "").strip():
                raise ContractError(f"{f!r} is required: a value with no {f} cannot be compared")
        if not self.comparable_when:
            raise ContractError(
                "comparable_when is required and may not be empty. State what would make a later "
                "reading comparable to this one -- you are the only person who still knows. "
                "If you genuinely believe nothing must match, say so explicitly with "
                "comparable_when=['*'] and write why in `note`."
            )
        if self.comparable_when == ["*"] and not self.note.strip():
            raise ContractError(
                "comparable_when=['*'] claims this reading is comparable to any other on the same "
                "instrument and subject. That is a strong claim; put the justification in `note`."
            )
        for key in self.comparable_when:
            if key == "*":
                continue
            name, _tol = _parse_key(key)
            if name in MANDATORY:
                continue
            if name not in self.conditions:
                raise ContractError(
                    f"comparable_when names {name!r} but conditions has no such key "
                    f"(has: {sorted(self.conditions)}). A contract that references a condition "
                    f"you did not record cannot be checked."
                )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Measurement":
        return cls(**d)


def _parse_key(key: str) -> tuple[str, float | None]:
    m = _TOL.match(key)
    if m:
        return m.group("key"), float(m.group("tol"))
    return key, None


def _within(a: Any, b: Any, tol: float) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def compare(a: Measurement, b: Measurement, *, varying: str | None = None) -> Verdict:
    """Are these two measurements comparable, varying exactly `varying`?

    Returns a Verdict; it never raises on incomparability. Read it -- that is the point.
    """
    reasons: list[str] = []
    unknowns: list[str] = []
    checked: list[str] = []

    # A confounder either side DECLARED it did not control. Knowledge, not absence of it.
    for m, tag in ((a, "a"), (b, "b")):
        for c in m.known_confounded_by:
            if c != varying:
                reasons.append(
                    f"{tag} declares itself confounded by {c!r} (known_confounded_by)")

    # Retroactive demotion: a confounder we know about NOW that a record predates and did not
    # capture. This is the whole answer to "we cannot enumerate confounders pre-emptively" --
    # discovery propagates backwards, and an old reading stops looking clean the moment we
    # learn what it failed to record.
    for cname, learned in sorted(KNOWN_CONFOUNDERS.items()):
        if cname == varying:
            continue
        for m, tag in ((a, "a"), (b, "b")):
            if cname in m.conditions:
                continue
            predates = cname not in (m.confounders_known_at_store or [])
            unknowns.append(
                f"{cname!r} is a known confounder (learned {learned}) and {tag} does not record "
                f"it" + (" -- taken before we knew it mattered" if predates else ""))

    if a.metric != b.metric:
        reasons.append(f"different metric: {a.metric!r} vs {b.metric!r}")
    for m in MANDATORY:
        av, bv = getattr(a, m), getattr(b, m)
        if av != bv:
            extra = (" -- different cap masks; these are not the same quantity"
                     if m == "instrument" else "")
            reasons.append(f"different {m}: {av!r} vs {bv!r}{extra}")

    # The UNION of both contracts. See decision 1.
    keys: list[str] = []
    for k in list(a.comparable_when) + list(b.comparable_when):
        if k not in keys:
            keys.append(k)

    if "*" in keys and len(keys) == 1:
        return Verdict(not reasons, tuple(reasons), tuple(unknowns), ("*",))

    if varying is not None:
        present = any(_parse_key(k)[0] == varying for k in keys) or (
            varying in a.conditions or varying in b.conditions)
        if not present:
            reasons.append(
                f"varying={varying!r} is not a recorded condition on either measurement, so the "
                f"claim that it is what differs is unverifiable")

    for key in keys:
        if key == "*":
            continue
        name, tol = _parse_key(key)
        if name in MANDATORY or name == varying:
            continue
        if name not in a.conditions or name not in b.conditions:
            missing = "a" if name not in a.conditions else "b"
            reasons.append(f"condition {name!r} required by a contract but not recorded on {missing}")
            continue
        av, bv = a.conditions[name], b.conditions[name]
        if tol is not None:
            if not _within(av, bv, tol):
                reasons.append(f"condition {name!r} differs beyond ±{tol:g}: {av!r} vs {bv!r}")
        elif av != bv:
            reasons.append(f"condition {name!r} differs: {av!r} vs {bv!r}")
        checked.append(name)

    return Verdict(not reasons, tuple(reasons), tuple(unknowns), tuple(checked))


def require_comparable(a: Measurement, b: Measurement, *, varying: str | None = None,
                       strict: bool = True) -> None:
    """Raise unless the comparison is licensed.

    strict=True (default) also raises on UNKNOWN. That is deliberate: the failures this
    module exists for were all UNKNOWNs treated as clean, so the safe default must be the
    one that stops. Pass strict=False to proceed on an unknown -- and then say so in prose.
    """
    v = compare(a, b, varying=varying)
    if not v or (strict and v.unknowns):
        raise Incomparable(str(v))


def delta(a: Measurement, b: Measurement, *, varying: str) -> float:
    """a.value - b.value, but only if the two are actually comparable. Raises otherwise."""
    require_comparable(a, b, varying=varying)
    return float(a.value) - float(b.value)


def load(path) -> list[Measurement]:
    """Read a JSONL store. Every record is re-validated -- a stored record with no contract is
    a defect to surface, not something to read past."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Measurement.from_dict(json.loads(line)))
            except (ContractError, TypeError, ValueError) as e:
                raise ContractError(f"{path}:{i}: {e}") from e
    return out


def store(path, m: Measurement) -> None:
    m.validate()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(m.to_dict()) + "\n")


def index(path) -> dict[str, Measurement]:
    """id -> Measurement, for resolving citations found in prose."""
    return {m.id: m for m in load(path)}


def resolve_citations(text: str, store_path) -> list[tuple[str, Measurement | None]]:
    """Find every [m:<id>] in a document and resolve it against the store.

    An unresolvable citation is returned as (id, None) rather than skipped: a doc pointing at a
    measurement that does not exist is exactly the rot this is meant to expose, and silently
    dropping it would reproduce the problem one layer up.
    """
    idx = index(store_path)
    return [(cid, idx.get(cid)) for cid in CITE.findall(text)]
