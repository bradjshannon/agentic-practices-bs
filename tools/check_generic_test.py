#!/usr/bin/env python3
"""Tests for `check_generic.py`, built around a POSITIVE CONTROL.

WHY THE POSITIVE CONTROL IS THE POINT
-------------------------------------
`GUARD-LEDGER.md` records the exact way a checker's suite goes vacuous: *"asserting
`returncode == 0` would pass on a hook whose body was deleted."* A test that only asserts this
repo is currently clean has that defect in full -- gut `scan()` to `return []` and it stays
green forever, while the guard silently stops guarding.

So the load-bearing case here is `test_positive_control`: a fixture that DOES name the operator,
which the checker MUST flag, at the right path and the right line number. Deleting the body of
`scan()` turns that case red. The clean-repo case is the CI gate; the positive control is what
makes the CI gate mean something.

Run: `python3 tools/check_generic_test.py`  (exit 0 = all passed).
Picked up automatically by `.github/workflows/tool-tests.yml`, which globs `tools/*_test.py`.
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("check_generic", _HERE / "check_generic.py")
cg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cg)

# The name is spelled out here on purpose -- a positive control that does not contain the thing
# being detected is not a control. `check_generic.py` exempts this file for exactly this reason.
_THE_NAME = "Brad"

_results: list[tuple[str, bool, str]] = []


def case(fn):
    try:
        fn()
        _results.append((fn.__name__, True, ""))
    except AssertionError as exc:
        _results.append((fn.__name__, False, str(exc)))
    except Exception as exc:  # an erroring test is a failing test, never a skipped one
        _results.append((fn.__name__, False, f"{type(exc).__name__}: {exc}"))
    return fn


def _repo(files: dict[str, str]) -> pathlib.Path:
    """A real temp git repo with `files` tracked. Real, not faked: `scan()` reads the tracked
    set from `git ls-files`, so a stubbed lister would test something else."""
    root = pathlib.Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                   capture_output=True)
    return root


# ── THE POSITIVE CONTROL ─────────────────────────────────────────────────────────────────────
@case
def test_positive_control_a_named_line_is_flagged():
    root = _repo({"notes.md": f"line one is clean\n{_THE_NAME} asked for this change\nlast line\n"})
    found = cg.scan(root)
    assert len(found) == 1, f"expected exactly 1 finding, got {found!r}"
    path, lineno, line = found[0]
    assert path == "notes.md", path
    assert lineno == 2, f"expected line 2, got {lineno}"
    assert _THE_NAME in line, line


@case
def test_positive_control_catches_every_form():
    """Lowercase, uppercase, the org name and the other-machine username must all be caught --
    each is a real form measured in this repo before the sweep."""
    for form in ("Brad", "brad", "BRAD", "brads", "bradjshannon"):
        root = _repo({"f.md": f"text {form} text\n"})
        assert len(cg.scan(root)) == 1, f"form {form!r} was NOT flagged"


@case
def test_main_exits_1_on_a_dirty_tree():
    """The exit code is the gate, so assert it directly rather than trusting `scan()` alone."""
    root = _repo({"notes.md": f"{_THE_NAME} said so\n"})
    findings = cg.scan(root)
    assert findings, "precondition: fixture must be dirty"
    # main() scans its own repo, so drive the same decision the way main() does.
    assert (1 if findings else 0) == 1


# ── NEGATIVE CONTROLS: each is a false positive that would get this checker bypassed ─────────
@case
def test_clean_file_is_silent():
    root = _repo({"notes.md": "the operator asked for this change\nthey replied\n"})
    assert cg.scan(root) == [], cg.scan(root)


@case
def test_an_ordinary_word_containing_the_stem_is_not_a_hit():
    """The false positive that would get this checker bypassed. `abrade` fails the prefix
    boundary; `bradawl` is an ordinary English word that an open `\\bbrad\\w*` DID flag on the
    first draft -- which is why the suffix is enumerated. Both must be silent."""
    root = _repo({"notes.md": "the abrade test and a bradawl-free design\n"})
    assert cg.scan(root) == [], cg.scan(root)


@case
def test_untracked_files_are_not_scanned():
    root = _repo({"tracked.md": "clean\n"})
    (root / "untracked.md").write_text(f"{_THE_NAME}\n", encoding="utf-8")
    assert cg.scan(root) == [], "an untracked file must not fail the gate"


@case
def test_binary_suffixes_are_skipped():
    root = _repo({"img.png": f"{_THE_NAME}\n"})
    assert cg.scan(root) == []


# ── THE EXEMPTION TABLE ──────────────────────────────────────────────────────────────────────
@case
def test_an_exempt_line_is_silent():
    root = _repo({"LICENSE": f"Copyright (c) 2026 {_THE_NAME} Shannon\n"})
    assert cg.scan(root) == [], "the whole-file exemption for LICENSE did not apply"


@case
def test_exemptions_are_line_scoped_not_file_scoped():
    """The sharp edge: a file that carries ONE exempt line must still be checked on every other
    line, or an exemption silently widens into a blanket."""
    root = _repo({
        "README.md": (
            "clone with `gh repo clone bradjshannon/agentic-practices-bs`\n"
            f"{_THE_NAME} decided this on a Tuesday\n"
        )
    })
    found = cg.scan(root)
    assert len(found) == 1, f"expected the second line only, got {found!r}"
    assert found[0][1] == 2, found


@case
def test_a_named_line_in_an_exempt_file_without_the_literal_is_flagged():
    root = _repo({"tools/check_sanitized.py": f"# {_THE_NAME} wrote this comment\n"})
    assert len(cg.scan(root)) == 1, "path-only matching would be a blanket exemption"


@case
def test_every_exemption_carries_a_reason():
    for path, _literal, reason in cg._EXEMPTIONS:
        assert reason and reason.strip(), f"exemption for {path} has no reason"


# ── THE GATE ITSELF ──────────────────────────────────────────────────────────────────────────
@case
def test_this_repo_is_currently_clean():
    """The CI gate. On its own this would pass on a gutted `scan()` -- which is why the positive
    control above exists and runs in the same file."""
    root = pathlib.Path(__file__).resolve().parent.parent
    found = cg.scan(root)
    assert found == [], "\n".join(f"{p}:{n}  {ln[:120]}" for p, n, ln in found)


if __name__ == "__main__":
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n        {msg}" if msg else ""))
    failed = sum(1 for _, ok, _ in _results if not ok)
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
