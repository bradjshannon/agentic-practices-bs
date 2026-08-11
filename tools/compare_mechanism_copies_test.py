#!/usr/bin/env python3
"""Tests for compare_mechanism_copies.py -- every verdict, in both directions.

WHY BOTH DIRECTIONS
-------------------
`mechanisms/GUARD-LEDGER.md` sets this repo's bar: a mechanism is not verified until it has been
observed FIRING when it should and observed STAYING SILENT when it should not. For a comparator
that means the positive control is not optional and is not one test: an IDENTICAL pair must report
IDENTICAL, and a differing pair must report the difference. A comparator that reported DIFFERENT
for everything would look exactly as useful as this one on the real population -- which is
currently divergent -- and nothing else in the suite would catch it.

WHY TEMP FIXTURES AND NEVER THE REAL DIRECTORIES
-------------------------------------------------
A test that reads this machine's hooks directory describes ONE machine and passes vacuously on any
other, including a CI runner with nothing installed, where "no findings" is an absence of subject
matter rather than a pass. Every case below builds its own roots in a temp dir, so the assertions
are about this script's LOGIC. The subject is imported relative to THIS file, so a green run is
evidence about the banked copy and not about whatever happens to be installed -- the specific
mistake `GUARD-LEDGER.md` records having shipped once, where a banked test silently exercised an
installed copy and a regression in the banked one could not have failed it.

Run: python tools/compare_mechanism_copies_test.py
"""
from __future__ import annotations

import io
import sys
import tempfile
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_mechanism_copies as cmc  # noqa: E402

_failures: list[str] = []

# Two sources that differ in ONE line, and a third that shares almost nothing. Kept small and
# explicit so every asserted number below can be checked by eye rather than trusted.
SRC_A = "import sys\n\n\ndef run():\n    return 1\n"
SRC_A_CRLF = SRC_A.replace("\n", "\r\n")
SRC_A_ONE_EDIT = "import sys\n\n\ndef run():\n    return 2\n"
SRC_UNRELATED = "from pathlib import Path\n\n\nclass Other:\n    pass\n"


def check(what: str, got, want) -> None:
    if got != want:
        _failures.append(f"{what}: got {got!r}, want {want!r}")
        print(f"    FAIL {what}: got {got!r}, want {want!r}")
    else:
        print(f"    ok   {what}")


class Fixture:
    """Two or more labelled roots in a temp dir. Nothing outside the temp dir is ever touched."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.roots: dict[str, Path] = {}

    def root(self, label: str) -> Path:
        path = self.base / label
        path.mkdir(parents=True, exist_ok=True)
        self.roots[label] = path
        return path

    def put(self, label: str, name: str, text: str) -> Path:
        path = self.root(label) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def rows(self, include=("*.py",)) -> dict[str, dict]:
        return {r["mechanism"]: r for r in cmc.compare(self.roots, include)}

    def __del__(self) -> None:
        try:
            self._tmp.cleanup()
        except Exception:
            pass


# ── THE POSITIVE CONTROL ─────────────────────────────────────────────────────────────────────

def test_identical_pair_reports_identical():
    """THE POSITIVE CONTROL. A comparator that cannot say "these are the same" is a comparator
    that reports drift unconditionally, which is indistinguishable from a broken one on a
    population that is currently drifted."""
    f = Fixture()
    f.put("bank", "guard.py", SRC_A)
    f.put("installed", "guard.py", SRC_A)
    row = f.rows()["guard.py"]
    check("identical pair verdict", row["verdict"], cmc.IDENTICAL)
    check("identical pair similarity", row["similarity"], 1.0)
    check("identical pair changed lines", row["changed_lines"], 0)
    check("identical pair exits 0", cmc.exit_code(list(f.rows().values())), 0)


def test_differing_pair_reports_the_difference():
    """The other half of the control: a real one-line difference must be reported, and reported
    with a magnitude rather than a boolean."""
    f = Fixture()
    f.put("bank", "guard.py", SRC_A)
    f.put("installed", "guard.py", SRC_A_ONE_EDIT)
    row = f.rows()["guard.py"]
    check("differing pair verdict", row["verdict"], cmc.DIFFERENT)
    check("one edited line is one deletion plus one addition", row["changed_lines"], 2)
    check("similarity is below 1 but not near 0", 0.5 < row["similarity"] < 1.0, True)
    check("differing pair exits 1", cmc.exit_code(list(f.rows().values())), 1)


# ── REQUIREMENT 1: LINE ENDINGS ──────────────────────────────────────────────────────────────

def test_crlf_only_difference_is_identical():
    """The measured confound. A byte comparison calls these two files 100% changed, which is how
    the real divergence stayed invisible underneath: every file looked maximally different, so no
    file looked notable."""
    f = Fixture()
    f.put("bank", "guard.py", SRC_A)
    f.put("installed", "guard.py", SRC_A_CRLF)
    check("CRLF vs LF is not a difference", f.rows()["guard.py"]["verdict"], cmc.IDENTICAL)


def test_byte_comparison_would_have_disagreed():
    """The control ON that control: prove the two fixtures really are byte-different, so the test
    above is demonstrating normalisation rather than comparing a file to itself."""
    check("the CRLF fixture is genuinely different bytes",
          SRC_A.encode() != SRC_A_CRLF.encode(), True)


def test_a_missing_final_newline_is_not_a_difference():
    """Same class as line endings, and stated in the docstring: splitting into lines makes it
    invisible. Asserted so the claim is checked rather than assumed."""
    f = Fixture()
    f.put("bank", "guard.py", SRC_A)
    f.put("installed", "guard.py", SRC_A.rstrip("\n"))
    check("trailing newline is not a difference", f.rows()["guard.py"]["verdict"], cmc.IDENTICAL)


# ── REQUIREMENT 2: MAGNITUDE, NOT A BOOLEAN ──────────────────────────────────────────────────

def test_a_near_rewrite_scores_lower_than_a_one_line_edit():
    """0.59 and 0.31 are different situations. If the number cannot separate them it is a boolean
    wearing a decimal point."""
    f = Fixture()
    f.put("bank", "small.py", SRC_A)
    f.put("installed", "small.py", SRC_A_ONE_EDIT)
    f.put("bank", "big.py", SRC_A)
    f.put("installed", "big.py", SRC_UNRELATED)
    rows = f.rows()
    small, big = rows["small.py"]["similarity"], rows["big.py"]["similarity"]
    check("both are DIFFERENT", (rows["small.py"]["verdict"], rows["big.py"]["verdict"]),
          (cmc.DIFFERENT, cmc.DIFFERENT))
    check("a near-rewrite scores strictly lower than a one-line edit", big < small, True)


def test_line_counts_are_reported_per_root_without_ranking_them():
    """Line counts are data for a human. The tool must not turn "shorter" into a verdict --
    sanitisation and drift are indistinguishable to a differ."""
    f = Fixture()
    f.put("bank", "guard.py", SRC_A + "extra = 1\n")
    f.put("installed", "guard.py", SRC_A)
    row = f.rows()["guard.py"]
    check("both line counts present", (row["lines"]["bank"], row["lines"]["installed"]), (6, 5))
    check("no direction word appears in the row",
          any(k in row for k in ("newer", "ahead", "behind", "authoritative", "source")), False)


# ── REQUIREMENT 3: MISSING IS A FINDING ──────────────────────────────────────────────────────

def test_absent_on_one_side_is_missing_not_different():
    f = Fixture()
    f.put("bank", "only_banked.py", SRC_A)
    f.root("installed")
    row = f.rows()["only_banked.py"]
    check("absent one side verdict", row["verdict"], cmc.MISSING)
    check("names where it is absent", row["absent_from"], ["installed"])
    check("names where it is present", row["present_in"], ["bank"])
    check("MISSING exits 1", cmc.exit_code(list(f.rows().values())), 1)


def test_missing_is_reported_in_both_directions():
    """Banked-but-not-installed and installed-but-never-banked are both findings, and this repo
    has been bitten by each. A comparator that walked only one root would see one of them."""
    f = Fixture()
    f.put("bank", "only_banked.py", SRC_A)
    f.put("installed", "only_installed.py", SRC_A)
    rows = f.rows()
    check("banked-only is found", rows["only_banked.py"]["absent_from"], ["installed"])
    check("installed-only is found", rows["only_installed.py"]["absent_from"], ["bank"])


def test_a_root_that_does_not_exist_makes_everything_missing_not_identical():
    """The silent-skip failure, one layer up: a mistyped or absent root must not produce an empty
    comparison that reads as agreement."""
    f = Fixture()
    f.put("bank", "guard.py", SRC_A)
    f.roots["installed"] = f.base / "not-here"
    rows = f.rows()
    check("verdict against an absent root", rows["guard.py"]["verdict"], cmc.MISSING)
    check("absent root exits 1", cmc.exit_code(list(rows.values())), 1)


def test_the_union_is_compared_never_the_intersection():
    f = Fixture()
    f.put("bank", "a.py", SRC_A)
    f.put("bank", "b.py", SRC_A)
    f.put("installed", "b.py", SRC_A)
    f.put("installed", "c.py", SRC_A)
    check("every named mechanism appears", sorted(f.rows()), ["a.py", "b.py", "c.py"])


# ── REQUIREMENT 4: UNREADABLE IS NEVER OK ────────────────────────────────────────────────────

def test_an_unreadable_copy_is_could_not_check_not_identical():
    """Two unreadable files must not compare equal to each other. Returning "" on a read failure
    is the obvious implementation and it lands both of them in the OK bucket."""
    f = Fixture()
    f.put("bank", "guard.py", SRC_A)
    path = f.root("installed") / "guard.py"
    path.write_bytes(b"\xff\xfe\x00\x00 not utf-8 \xc3\x28")
    row = f.rows()["guard.py"]
    check("unreadable verdict", row["verdict"], cmc.COULD_NOT_CHECK)
    check("names the root it could not read", list(row["unreadable_in"]), ["installed"])
    check("could-not-check exits 2", cmc.exit_code(list(f.rows().values())), 2)


def test_could_not_check_outranks_a_mere_difference():
    """Exit 2 must win over exit 1: a run that could not see part of its subject must not report
    a backlog it did not actually measure."""
    f = Fixture()
    f.put("bank", "readable.py", SRC_A)
    f.put("installed", "readable.py", SRC_UNRELATED)
    f.put("bank", "unreadable.py", SRC_A)
    (f.root("installed") / "unreadable.py").write_bytes(b"\xc3\x28\xff")
    rows = list(f.rows().values())
    check("a difference alone would be 1",
          cmc.exit_code([r for r in rows if r["mechanism"] == "readable.py"]), 1)
    check("with an unreadable copy the run is 2", cmc.exit_code(rows), 2)


def test_two_unreadable_copies_do_not_compare_equal():
    f = Fixture()
    (f.root("bank") / "g.py").write_bytes(b"\xff\xfe\x28")
    (f.root("installed") / "g.py").write_bytes(b"\xff\xfe\x28")
    check("identical bytes, both unreadable, still not OK",
          f.rows()["g.py"]["verdict"], cmc.COULD_NOT_CHECK)


# ── N-WAY BEHAVIOUR ──────────────────────────────────────────────────────────────────────────

def test_three_roots_report_the_worst_agreeing_pair():
    """With three copies the useful number is how far apart the two furthest are. An average
    would let one in-step pair mask a rewritten third copy."""
    f = Fixture()
    f.put("bank", "g.py", SRC_A)
    f.put("installed", "g.py", SRC_A)
    f.put("public", "g.py", SRC_UNRELATED)
    row = f.rows()["g.py"]
    check("three-root verdict", row["verdict"], cmc.DIFFERENT)
    check("the worst pair is named", sorted(row["worst_pair"]), ["bank", "public"])
    check("two agreeing copies do not mask the third", row["similarity"] < 0.5, True)


def test_all_three_identical_is_identical():
    f = Fixture()
    for label in ("bank", "installed", "public"):
        f.put(label, "g.py", SRC_A)
    check("three identical copies", f.rows()["g.py"]["verdict"], cmc.IDENTICAL)
    check("three identical copies exit 0", cmc.exit_code(list(f.rows().values())), 0)


# ── HOUSEKEEPING ─────────────────────────────────────────────────────────────────────────────

def test_pycache_is_never_compared():
    """Compiler output is derived from a source this tool already reads. Reporting it would be
    reporting the same divergence twice, once as an unreadable binary blob."""
    f = Fixture()
    f.put("bank", "g.py", SRC_A)
    f.put("installed", "g.py", SRC_A)
    (f.root("installed") / "__pycache__").mkdir(exist_ok=True)
    (f.root("installed") / "__pycache__" / "g.cpython-311.pyc").write_bytes(b"\x00\x01")
    check("only the source is compared", sorted(f.rows()), ["g.py"])


def test_include_globs_are_honoured():
    f = Fixture()
    f.put("bank", "g.py", SRC_A)
    f.put("bank", "notes.md", "# hi\n")
    f.put("installed", "g.py", SRC_A)
    check("default include is python only", sorted(f.rows()), ["g.py"])
    check("widening the glob finds the rest",
          sorted(f.rows(include=("*.py", "*.md"))), ["g.py", "notes.md"])


def test_subdirectories_are_keyed_by_relative_path():
    """Keyed by relative path, not bare filename, so two roots that organise into subdirectories
    are compared like with like rather than colliding on a shared basename."""
    f = Fixture()
    f.put("bank", "sub/g.py", SRC_A)
    f.put("installed", "sub/g.py", SRC_A)
    f.put("installed", "g.py", SRC_A)
    rows = f.rows()
    check("nested path is its own key", sorted(rows), ["g.py", "sub/g.py"])
    check("the nested pair matches", rows["sub/g.py"]["verdict"], cmc.IDENTICAL)
    check("the top-level singleton is MISSING", rows["g.py"]["verdict"], cmc.MISSING)


def _expect_cli_refusal(argv: list[str]) -> int | None:
    """Run the CLI expecting argparse to refuse. argparse writes usage to stderr, which is
    swallowed here so a passing run does not print text that reads like a failure in a CI log."""
    try:
        with redirect_stderr(io.StringIO()):
            cmc.main(argv)
    except SystemExit as exc:
        return exc.code
    return None


def test_cli_refuses_a_single_root():
    """Comparing one copy against nothing is not a comparison, and must not exit 0 having done
    nothing -- the bare-`exit 0` wrapper failure this corpus opens with."""
    code = _expect_cli_refusal(["--dir", "only=."])
    check("one --dir exits non-zero", code not in (None, 0), True)


def test_cli_refuses_one_label_repeated_with_no_second_copy():
    """A repeated label is ONE copy over several directories, so two --dir with the same label
    is still only one copy and must be refused for the same reason a single --dir is."""
    code = _expect_cli_refusal(["--dir", "a=.", "--dir", "a=."])
    check("one repeated label exits non-zero", code not in (None, 0), True)


def test_a_copy_may_span_several_directories():
    """THE FALSE-MISSING FIX, and it was found by running the tool against the real population.
    `SCOPE-AND-VENDORING.md` records the same defect done by hand: two hooks banked in
    `mechanisms/scripts/` rather than `mechanisms/hooks/` were surveyed by directory and declared
    machine-only, when they were banked and byte-identical. A comparator that could only take one
    directory per copy reproduces that error mechanically, on every run."""
    f = Fixture()
    f.put("bank_a", "in_hooks.py", SRC_A)
    f.put("bank_b", "in_scripts.py", SRC_A)
    f.put("installed", "in_hooks.py", SRC_A)
    f.put("installed", "in_scripts.py", SRC_A)

    split = {"bank": [f.roots["bank_a"], f.roots["bank_b"]], "installed": [f.roots["installed"]]}
    rows = {r["mechanism"]: r for r in cmc.compare(split, ("*.py",))}
    check("both halves of a split copy are found",
          (rows["in_hooks.py"]["verdict"], rows["in_scripts.py"]["verdict"]),
          (cmc.IDENTICAL, cmc.IDENTICAL))
    check("a split copy that matches exits 0", cmc.exit_code(list(rows.values())), 0)

    # THE CONTROL: the same trees compared with only the first bank directory must produce the
    # false MISSING, or the fix above is not demonstrating anything.
    one_dir = {"bank": [f.roots["bank_a"]], "installed": [f.roots["installed"]]}
    naive = {r["mechanism"]: r for r in cmc.compare(one_dir, ("*.py",))}
    check("comparing by one directory reproduces the false MISSING",
          naive["in_scripts.py"]["verdict"], cmc.MISSING)


def test_a_name_present_in_two_directories_of_one_copy_is_ambiguous():
    """AMBIGUOUS, not DIFFERENT, and this is the verdict the first version of this tool lacked.

    When one copy contains the same mechanism twice there is no single subject; picking one is
    deciding which is authoritative, which is the thing this tool refuses to do one level up. The
    measured case: the doubled file matched the other copy EXACTLY under one path and differed by
    eighty lines under the other, so a silent tie-break chose which of two true statements got
    printed."""
    f = Fixture()
    f.put("bank_a", "dup.py", SRC_UNRELATED)   # the tie-break would pick this one
    f.put("bank_b", "dup.py", SRC_A)           # ...and this one matches `installed` exactly
    f.put("installed", "dup.py", SRC_A)
    split = {"bank": [f.roots["bank_a"], f.roots["bank_b"]], "installed": [f.roots["installed"]]}
    rows = {r["mechanism"]: r for r in cmc.compare(split, ("*.py",))}
    row = rows["dup.py"]
    check("doubled copy verdict", row["verdict"], cmc.AMBIGUOUS)
    check("it names the label that doubles it", list(row["doubled_in"]), ["bank"])
    check("it names both paths", len(row["doubled_in"]["bank"]), 2)
    check("AMBIGUOUS exits 1", cmc.exit_code(list(rows.values())), 1)


def test_an_ambiguous_row_is_not_reported_as_agreement():
    """The failure mode that makes AMBIGUOUS worth a verdict rather than a warning: if the
    tie-break happens to pick the matching copy, a doubled mechanism would report IDENTICAL and
    the run would exit 0 over a real finding."""
    f = Fixture()
    f.put("bank_a", "dup.py", SRC_A)           # tie-break picks this; it matches installed
    f.put("bank_b", "dup.py", SRC_UNRELATED)   # ...while this one does not
    f.put("installed", "dup.py", SRC_A)
    split = {"bank": [f.roots["bank_a"], f.roots["bank_b"]], "installed": [f.roots["installed"]]}
    rows = list(cmc.compare(split, ("*.py",)))
    check("a lucky tie-break still does not read as agreement", rows[0]["verdict"], cmc.AMBIGUOUS)
    check("and does not exit 0", cmc.exit_code(rows), 1)


def test_ambiguity_is_scoped_to_the_label_that_has_it():
    """A copy that is split but has no collision must stay a normal verdict -- otherwise the new
    verdict would fire on every split copy and stop meaning anything."""
    f = Fixture()
    f.put("bank_a", "one.py", SRC_A)
    f.put("bank_b", "two.py", SRC_A)
    f.put("installed", "one.py", SRC_A)
    f.put("installed", "two.py", SRC_A)
    split = {"bank": [f.roots["bank_a"], f.roots["bank_b"]], "installed": [f.roots["installed"]]}
    rows = {r["mechanism"]: r for r in cmc.compare(split, ("*.py",))}
    check("a split copy with no collision is unaffected",
          (rows["one.py"]["verdict"], rows["two.py"]["verdict"]),
          (cmc.IDENTICAL, cmc.IDENTICAL))
    check("no collision means exit 0", cmc.exit_code(list(rows.values())), 0)


def test_dir_spec_needs_a_label():
    import argparse
    for bad in ("nolabel", "=/tmp/x", "  =/tmp/x"):
        try:
            cmc.parse_dir(bad)
            check(f"{bad!r} should be rejected", "accepted", "rejected")
        except argparse.ArgumentTypeError:
            check(f"{bad!r} is rejected", True, True)


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
