#!/usr/bin/env python3
"""Tests for `check_sanitized.py`'s pattern table.

Run: python -m pytest tools/check_sanitized_test.py -q   (stdlib unittest, no deps)

WHY THIS FILE EXISTS
--------------------
This checker had **no tests at all**, and it was reporting a public repo clean while two real
operator home paths sat in it. The `operator-path` pattern was `C:\\\\Users\\\\brads` — the *other*
workstation's username — so `C:\\Users\\brad\\...`, this machine's, never matched. CI was green
the entire time.

That is this repo's own recurring failure written into its own guard: a check that cannot fail
reports clean forever, and a green instrument is what stops anyone running the one command that
would have caught it. `GUARD-LEDGER.md` states the same thing one layer up — asserting
`returncode == 0` passes on a checker whose body was deleted.

So every pattern here gets BOTH directions: a string it must flag, and a near-miss it must not.
"""
from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CS = _load("check_sanitized_under_test", "check_sanitized.py")


def _flags(text: str) -> set[str]:
    """Categories that fire on one line of text."""
    return {cat for cat, pat in CS._PATTERNS if pat.search(text)}


class OperatorPathCoversBothWorkstations(unittest.TestCase):
    """The defect this file was created for.

    Measured 2026-08-11: the estate has two workstations with different usernames, and the
    pattern named only one of them. Two real paths from the uncovered one were sitting in this
    public repo with the job passing.
    """

    def test_the_other_workstation_path_is_flagged(self):
        """POSITIVE CONTROL for the pattern that already worked -- without this, a regression
        that broke both would look like the fix below simply not being needed."""
        self.assertIn("operator-path", _flags(r"C:\Users\brads\Documents\GitHub\repo"))

    def test_this_workstation_path_is_flagged(self):
        """The gap. Before the fix this returned an empty set."""
        self.assertIn("operator-path", _flags(r"C:\Users\brad\Documents\GitHub\repo"))

    def test_a_forward_slash_variant_is_flagged(self):
        self.assertIn("operator-path", _flags("C:/Users/brad/Documents"))

    def test_a_longer_name_is_not_a_false_positive(self):
        """NEGATIVE CONTROL: the fix must not fire on any username that merely starts the same
        way. A guard that cries wolf gets bypassed and takes its true positives with it."""
        self.assertNotIn("operator-path", _flags(r"C:\Users\bradley\Documents"))

    def test_ordinary_prose_is_untouched(self):
        self.assertEqual(_flags("the operator's home directory is not named here"), set())


class TheTableItselfIsExercised(unittest.TestCase):
    """Guards against the whole table being emptied or renamed out from under these tests."""

    def test_patterns_exist_and_are_compiled(self):
        self.assertTrue(CS._PATTERNS, "an empty pattern table would pass every test above vacuously")
        for cat, pat in CS._PATTERNS:
            self.assertIsInstance(cat, str)
            self.assertTrue(hasattr(pat, "search"), f"{cat} is not a compiled pattern")

    def test_a_known_host_leak_still_fires(self):
        """A second live category, so a change that neutered only `operator-path` is visible."""
        self.assertIn("host", _flags("https://somebox.tail1a2b3c.ts.net:9443/"))


if __name__ == "__main__":
    unittest.main()
