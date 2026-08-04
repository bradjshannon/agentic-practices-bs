#!/usr/bin/env python3
"""Tests for check_workstation.py -- both directions for every verdict.

WHY BOTH DIRECTIONS
-------------------
`mechanisms/GUARD-LEDGER.md` sets this repo's bar: a mechanism is not verified until it has been
observed FIRING when it should and observed STAYING SILENT when it should not. A check that only
ever fires is indistinguishable from a check that always fires, and the latter gets switched off
-- taking its true positives with it. So every verdict below is asserted twice: once on a fixture
that should produce it, and once on the near-identical fixture that should not.

WHY A TEMP FIXTURE AND NEVER THE REAL ~/.claude
------------------------------------------------
A suite that reads the live hooks directory describes ONE machine. It would pass vacuously on any
other -- including a CI runner with nothing installed, where "no gaps found" is not a pass, it is
an absence of subject matter. Every case here builds its own catalogue, hooks directory, settings
file and manifest in a temp dir, so the assertions are about this script's LOGIC and hold
identically on any machine. The subject is imported relative to this file, never from a hooks
directory, so a green run is evidence about the banked copy.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_workstation as cw  # noqa: E402

# A file that reads a hook payload is an event hook; one that does not is a library. That is the
# discriminator under test, so the fixtures differ in exactly that respect and nothing else.
HOOK_SRC = "import sys, json\npayload = json.load(sys.stdin)\n"
LIB_SRC = "def helper():\n    return 1\n"
DISPATCHER_SRC = (
    "import sys, json\n"
    "payload = json.load(sys.stdin)\n"
    'CHECKS = ["delta_check.py"]\n'
)

_failures: list[str] = []


class Fixture:
    """A self-contained fake workstation: catalogue, hooks dir, settings, manifest."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.catalogue = root / "catalogue"
        self.hooks = root / "hooks"
        self.catalogue.mkdir()
        self.hooks.mkdir()
        self.settings = root / "settings.json"
        self.manifest = root / "mechanisms.toml"
        self.settings.write_text(json.dumps({"hooks": {}}), encoding="utf-8")

    def __enter__(self) -> Fixture:
        return self

    def __exit__(self, *exc) -> None:
        self._tmp.cleanup()

    def bank(self, name: str, src: str = HOOK_SRC) -> Fixture:
        (self.catalogue / name).write_text(src, encoding="utf-8")
        return self

    def install(self, name: str, src: str = HOOK_SRC) -> Fixture:
        (self.hooks / name).write_text(src, encoding="utf-8")
        return self

    def wire(self, *names: str, event: str = "PreToolUse") -> Fixture:
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        groups = data.setdefault("hooks", {}).setdefault(event, [])
        for name in names:
            groups.append({"hooks": [{"command": f"python ~/.claude/hooks/{name}"}]})
        self.settings.write_text(json.dumps(data), encoding="utf-8")
        return self

    def declare(self, name: str, want: str = "yes", sync: str = "manual",
                why: str = "because") -> Fixture:
        text = self.manifest.read_text(encoding="utf-8") if self.manifest.exists() else \
            "[mechanisms]\n"
        text += f'\n[mechanisms."{name}"]\nwant = "{want}"\nsync = "{sync}"\nwhy  = "{why}"\n'
        self.manifest.write_text(text, encoding="utf-8")
        return self

    def run(self) -> tuple[int, str]:
        """Run the checker end to end. Returns (exit code, combined output)."""
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            code = cw.main(["--manifest", str(self.manifest),
                            "--catalogue", str(self.catalogue),
                            "--hooks-dir", str(self.hooks),
                            "--settings", str(self.settings),
                            "--list"])
        return code, buf.getvalue()

    def verdict(self, name: str) -> str:
        manifest = cw.load_manifest(self.manifest)
        rows, _ = cw.evaluate(self.catalogue, self.hooks, [self.settings], manifest)
        for row in rows:
            if row["name"] == name:
                return row["verdict"]
        raise AssertionError(f"{name} produced no row at all")

    def exit_code(self) -> int:
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            return cw.main(["--manifest", str(self.manifest),
                            "--catalogue", str(self.catalogue),
                            "--hooks-dir", str(self.hooks),
                            "--settings", str(self.settings)])


def check(label: str, got, want) -> None:
    if got != want:
        _failures.append(f"{label}: expected {want!r}, got {got!r}")
        print(f"  FAIL  {label}: expected {want!r}, got {got!r}")
    else:
        print(f"  ok    {label}")


# ---------------------------------------------------------------------------------------------
# OK / MISSING -- installed and wired, versus every way that can fail
# ---------------------------------------------------------------------------------------------
def test_ok_fires_and_stays_silent() -> None:
    with Fixture() as f:
        f.bank("alpha_guard.py").install("alpha_guard.py").wire("alpha_guard.py")
        f.declare("alpha_guard.py", want="yes")
        check("OK: banked+installed+wired", f.verdict("alpha_guard.py"), cw.OK)
        check("OK: does not fail the run", f.exit_code(), 0)

    with Fixture() as f:  # same declaration, simply not installed
        f.bank("alpha_guard.py").declare("alpha_guard.py", want="yes")
        check("MISSING: wanted but not installed", f.verdict("alpha_guard.py"), cw.MISSING)
        check("MISSING: fails the run", f.exit_code(), 1)

    with Fixture() as f:  # installed, but nothing wires it -- presence is not force
        f.bank("alpha_guard.py").install("alpha_guard.py").declare("alpha_guard.py", want="yes")
        check("MISSING: installed but unwired", f.verdict("alpha_guard.py"), cw.MISSING)
        check("MISSING: unwired fails the run", f.exit_code(), 1)


def test_dispatched_counts_as_wired() -> None:
    """A check run in-process by a wired dispatcher is in force, though nothing wires it directly.

    Without this, moving a guard behind a dispatcher would report it as unadopted while it still
    ran on every turn -- and the honest-looking fix (re-wiring it directly) re-creates the
    duplication the dispatcher existed to remove.
    """
    with Fixture() as f:
        f.bank("gate.py", DISPATCHER_SRC).install("gate.py", DISPATCHER_SRC).wire("gate.py")
        f.bank("delta_check.py").install("delta_check.py")
        f.declare("gate.py").declare("delta_check.py")
        check("OK: dispatched by a wired gate", f.verdict("delta_check.py"), cw.OK)

    with Fixture() as f:  # identical, except the dispatcher itself is not wired
        f.bank("gate.py", DISPATCHER_SRC).install("gate.py", DISPATCHER_SRC)
        f.bank("delta_check.py").install("delta_check.py")
        f.declare("gate.py").declare("delta_check.py")
        check("MISSING: dispatcher itself unwired", f.verdict("delta_check.py"), cw.MISSING)


def test_library_is_not_reported_unwired() -> None:
    """A file that reads no hook payload cannot be wired, so demanding wiring of it is a lie.

    This is the false positive that a docstring-sniffing classifier produces on the real
    catalogue: a shared helper imported by several wired hooks, reported as an unadopted control.
    """
    with Fixture() as f:
        f.bank("echo_lib.py", LIB_SRC).install("echo_lib.py", LIB_SRC)
        f.declare("echo_lib.py", want="yes")
        check("OK: library installed, never wired", f.verdict("echo_lib.py"), cw.OK)
        check("OK: library does not fail the run", f.exit_code(), 0)

    with Fixture() as f:  # byte-identical situation except it DOES read a payload
        f.bank("echo_lib.py", HOOK_SRC).install("echo_lib.py", HOOK_SRC)
        f.declare("echo_lib.py", want="yes")
        check("MISSING: same file shape but reads stdin", f.verdict("echo_lib.py"), cw.MISSING)


# ---------------------------------------------------------------------------------------------
# DECLINED / UNEXPECTED -- the entire reason the manifest exists
# ---------------------------------------------------------------------------------------------
def test_declined_fires_and_never_counts_as_a_gap() -> None:
    with Fixture() as f:
        f.bank("foxtrot_guard.py").declare("foxtrot_guard.py", want="no", why="not this machine")
        check("DECLINED: banked, not installed, want=no",
              f.verdict("foxtrot_guard.py"), cw.DECLINED)
        check("DECLINED: exits 0 -- a decision, not a gap", f.exit_code(), 0)

    with Fixture() as f:  # the ONE-CHARACTER difference that is the whole feature
        f.bank("foxtrot_guard.py").declare("foxtrot_guard.py", want="yes")
        check("MISSING: same fixture, want flipped to yes",
              f.verdict("foxtrot_guard.py"), cw.MISSING)
        check("MISSING: and now it fails", f.exit_code(), 1)


def test_unexpected_fires_and_stays_silent() -> None:
    with Fixture() as f:
        f.bank("golf_guard.py").install("golf_guard.py").wire("golf_guard.py")
        f.declare("golf_guard.py", want="no")
        check("UNEXPECTED: declined but installed", f.verdict("golf_guard.py"), cw.UNEXPECTED)
        check("UNEXPECTED: fails the run", f.exit_code(), 1)

    with Fixture() as f:  # same want=no, but genuinely absent
        f.bank("golf_guard.py").declare("golf_guard.py", want="no")
        check("UNEXPECTED: silent when actually absent",
              f.verdict("golf_guard.py"), cw.DECLINED)


# ---------------------------------------------------------------------------------------------
# UNDECLARED -- an add is a question, not an update
# ---------------------------------------------------------------------------------------------
def test_undeclared_fires_and_stays_silent() -> None:
    with Fixture() as f:
        f.bank("hotel_guard.py")
        f.declare("other_guard.py", want="no")  # a manifest exists; this row simply is not in it
        check("UNDECLARED: in catalogue, no row", f.verdict("hotel_guard.py"), cw.UNDECLARED)
        check("UNDECLARED: fails the run", f.exit_code(), 1)
        _, out = f.run()
        check("UNDECLARED: names the one-line edit that answers it",
              'want = "yes"' in out and "[mechanisms." in out, True)

    with Fixture() as f:  # on the machine but never banked -- still undeclared
        f.install("hotel_guard.py").wire("hotel_guard.py")
        f.declare("other_guard.py", want="no")
        check("UNDECLARED: installed-only, no row", f.verdict("hotel_guard.py"), cw.UNDECLARED)

    with Fixture() as f:  # the row that makes it go quiet
        f.bank("hotel_guard.py").declare("hotel_guard.py", want="no")
        check("UNDECLARED: silent once declared", f.verdict("hotel_guard.py"), cw.DECLINED)
        check("UNDECLARED: silent run exits 0", f.exit_code(), 0)


# ---------------------------------------------------------------------------------------------
# DRIFTED -- and the case where drift cannot be detected at all
# ---------------------------------------------------------------------------------------------
def test_drifted_fires_and_stays_silent() -> None:
    with Fixture() as f:
        f.bank("india_guard.py", HOOK_SRC)
        f.install("india_guard.py", HOOK_SRC + "# a rule that was never banked\n")
        f.wire("india_guard.py").declare("india_guard.py", want="yes")
        check("DRIFTED: contents differ", f.verdict("india_guard.py"), cw.DRIFTED)
        check("DRIFTED: fails the run", f.exit_code(), 1)

    with Fixture() as f:  # byte-identical copies
        f.bank("india_guard.py", HOOK_SRC).install("india_guard.py", HOOK_SRC)
        f.wire("india_guard.py").declare("india_guard.py", want="yes")
        check("DRIFTED: silent when identical", f.verdict("india_guard.py"), cw.OK)
        check("DRIFTED: silent run exits 0", f.exit_code(), 0)

    with Fixture() as f:  # installed but never banked: nothing to compare, so not a failure
        f.install("juliet_guard.py").wire("juliet_guard.py").declare("juliet_guard.py")
        check("DRIFTED: unbanked cannot drift", f.verdict("juliet_guard.py"), cw.OK)
        _, out = f.run()
        check("DRIFTED: but 'not banked' is stated, not hidden", "not banked" in out, True)


def test_drift_is_named_even_when_another_verdict_wins() -> None:
    """Collapsing to one verdict per mechanism must not make a drifted file invisible."""
    with Fixture() as f:
        f.bank("kilo_guard.py", HOOK_SRC)
        f.install("kilo_guard.py", HOOK_SRC + "# drifted\n")  # installed, drifted, and UNWIRED
        f.declare("kilo_guard.py", want="yes")
        check("worst-wins: unwired outranks drifted", f.verdict("kilo_guard.py"), cw.MISSING)
        _, out = f.run()
        check("worst-wins: drift still named in the summary",
              "drifted from the banked copy: kilo_guard.py" in out, True)


# ---------------------------------------------------------------------------------------------
# Manifest handling: pins, validation, and the round-trip that must not destroy judgement
# ---------------------------------------------------------------------------------------------
def test_pin_behaves_as_wanted_but_says_it_is_unverified() -> None:
    with Fixture() as f:
        f.bank("lima_guard.py").install("lima_guard.py").wire("lima_guard.py")
        f.declare("lima_guard.py", want="pin:abc1234")
        check("pin: treated as wanted", f.verdict("lima_guard.py"), cw.OK)
        _, out = f.run()
        check("pin: reported as NOT verified", "revision NOT verified" in out, True)

    with Fixture() as f:
        f.bank("lima_guard.py").declare("lima_guard.py", want="pin:abc1234")
        check("pin: still MISSING when absent", f.verdict("lima_guard.py"), cw.MISSING)


def test_invalid_manifest_is_a_config_fault_not_a_conformance_result() -> None:
    for bad, label in ((('want = "maybe"'), "bad want"), (('want = "yes"\nsync = "sometimes"'),
                                                          "bad sync")):
        with Fixture() as f:
            f.bank("mike_guard.py")
            f.manifest.write_text(f'[mechanisms."mike_guard.py"]\n{bad}\n', encoding="utf-8")
            check(f"invalid manifest ({label}) exits 2", f.exit_code(), 2)

    with Fixture() as f:  # a valid one is not mistaken for invalid
        f.bank("mike_guard.py").declare("mike_guard.py", want="no", sync="never")
        check("valid manifest exits 0", f.exit_code(), 0)


def test_absent_manifest_exits_2_and_says_how_to_start() -> None:
    with Fixture() as f:
        f.bank("november_guard.py")
        check("no manifest at all exits 2", f.exit_code(), 2)
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            cw.main(["--manifest", str(f.manifest), "--catalogue", str(f.catalogue),
                     "--hooks-dir", str(f.hooks), "--settings", str(f.settings)])
        check("no manifest names --generate", "--generate" in buf.getvalue(), True)


def test_generate_round_trip_preserves_why_byte_for_byte() -> None:
    """The judgement half must survive a regeneration exactly, or the writer is worse than none."""
    with Fixture() as f:
        f.bank("oscar_guard.py").install("oscar_guard.py").wire("oscar_guard.py")
        f.bank("papa_guard.py")
        prose = "declined 2026-08-04: duplicates a repo-side gate; revisit if that gate moves"
        f.declare("oscar_guard.py", want="yes", sync="auto", why="carries the whole turn budget")
        f.declare("papa_guard.py", want="no", sync="never", why=prose)
        before = f.manifest.read_bytes()

        buf = io.StringIO()
        with redirect_stdout(buf):
            added = cw.generate(f.manifest, f.catalogue, f.hooks, [f.settings])
        check("round trip: nothing added when all declared", added, [])
        check("round trip: file is byte-identical", f.manifest.read_bytes(), before)
        check("round trip: prose survived verbatim",
              prose in f.manifest.read_text(encoding="utf-8"), True)

        with redirect_stdout(io.StringIO()):
            cw.generate(f.manifest, f.catalogue, f.hooks, [f.settings])
        check("round trip: idempotent across two runs", f.manifest.read_bytes(), before)


def test_generate_appends_only_and_never_rewrites() -> None:
    with Fixture() as f:
        f.bank("quebec_guard.py").install("quebec_guard.py").wire("quebec_guard.py")
        f.declare("quebec_guard.py", want="no", why="hand-authored decision")
        f.bank("romeo_guard.py")  # undeclared: the only thing generate may touch
        before = f.manifest.read_text(encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            added = cw.generate(f.manifest, f.catalogue, f.hooks, [f.settings])
        after = f.manifest.read_text(encoding="utf-8")
        check("generate: appended the undeclared row", added, ['romeo_guard.py  want="no"'])
        check("generate: existing bytes untouched", after.startswith(before), True)
        check("generate: did NOT overwrite a hand-authored decision",
              cw.load_manifest(f.manifest)["quebec_guard.py"]["want"], "no")
        check("generate: new row's why is an explicit placeholder, not invented",
              cw.load_manifest(f.manifest)["romeo_guard.py"]["why"], cw.PLACEHOLDER_WHY)


def test_generate_derives_want_from_what_is_actually_in_force() -> None:
    with Fixture() as f:
        f.bank("sierra_guard.py").install("sierra_guard.py").wire("sierra_guard.py")
        f.bank("tango_guard.py")  # banked, not installed
        f.install("uniform_guard.py")  # installed, not wired, not banked
        with redirect_stdout(io.StringIO()):
            cw.generate(f.manifest, f.catalogue, f.hooks, [f.settings])
        rows = cw.load_manifest(f.manifest)
        check("generate: in-force -> yes", rows["sierra_guard.py"]["want"], "yes")
        check("generate: absent -> no", rows["tango_guard.py"]["want"], "no")
        check("generate: installed-but-inert -> no", rows["uniform_guard.py"]["want"], "no")
        check("generate: default sync is manual", rows["sierra_guard.py"]["sync"], "manual")


def test_unreadable_settings_is_stated_not_swallowed() -> None:
    """A config this cannot parse must never render as 'nothing is wired'."""
    with Fixture() as f:
        f.bank("victor_guard.py").install("victor_guard.py")
        f.declare("victor_guard.py", want="yes")
        f.settings.write_text("{not json", encoding="utf-8")
        _, out = f.run()
        check("unreadable settings is reported", "UNREADABLE" in out, True)

    with Fixture() as f:
        f.bank("victor_guard.py").install("victor_guard.py").wire("victor_guard.py")
        f.declare("victor_guard.py", want="yes")
        _, out = f.run()
        check("readable settings says nothing about it", "UNREADABLE" in out, False)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    for test in TESTS:
        print(f"{test.__name__}:")
        test()
    print()
    if _failures:
        print(f"FAILED: {len(_failures)} assertion(s)")
        for line in _failures:
            print(f"  - {line}")
        return 1
    print(f"all assertions passed across {len(TESTS)} test(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
