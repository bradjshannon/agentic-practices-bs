#!/usr/bin/env python3
"""Tests for commit_verify.

WHY THIS FILE EXISTS AT ALL. commit_verify was shipped with a hand-run "5/5 against a
throwaway repo", which left no artifact -- so the tool became MANDATORY (lying_command_guard
blocks raw `git commit` and names it as the replacement) while carrying zero regression
coverage. The first defect found in it after that was a crash on any commit message
containing an arrow, i.e. on this project's normal prose.

The tool's whole promise is "cannot half-succeed", so the weight here is on the REFUSAL
cases: a postcondition that stops being checked is silent by construction, which is the
exact failure commit_verify was built to prevent. A test that only proves the happy path
would pass on a version that verified nothing.

Every case runs against a REAL throwaway git repo with a REAL bare remote -- no mocking of
git. Mocked git cannot catch an encoding fault on the pipe to `git commit`, which is what
the regression below actually was.

Run:  py -3 mechanisms/scripts/commit_verify_test.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CV = Path(__file__).resolve().parent / "commit_verify.py"

FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def run_cv(repo, paths, message, *, push=False, extra=()):
    """Invoke commit_verify as a SUBPROCESS with the message on stdin.

    Deliberately not an in-process import: the encoding bug lived in how the child
    process was spawned and how stdin was decoded, so importing `run()` and passing a
    str would have skipped the whole defective path. The bug was in the plumbing, so
    the test has to exercise the plumbing.
    """
    argv = [sys.executable, str(CV), "--repo", str(repo)]
    for p in paths:
        argv += ["--path", p]
    if push:
        argv.append("--push")
    argv += list(extra)
    p = subprocess.run(argv, input=message.encode("utf-8"),
                       capture_output=True)
    out = (p.stdout or b"").decode("utf-8", "replace")
    err = (p.stderr or b"").decode("utf-8", "replace")
    return p.returncode, out, err


class Sandbox:
    """A real repo + real bare remote, seeded with one commit so HEAD exists."""

    def __enter__(self):
        self.root = Path(tempfile.mkdtemp(prefix="cvtest-"))
        self.repo = self.root / "repo"
        self.bare = self.root / "bare"
        self.repo.mkdir()
        self.bare.mkdir()
        subprocess.run(["git", "-C", str(self.bare), "init", "--bare", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "init", "-q", "-b", "main"], check=True)
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "config", "user.name", "test")
        git(self.repo, "remote", "add", "origin", str(self.bare))
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        git(self.repo, "add", "seed.txt")
        git(self.repo, "commit", "-q", "-m", "seed")
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, text):
        (self.repo / rel).write_text(text, encoding="utf-8")

    def head_subject(self):
        return git(self.repo, "log", "-1", "--format=%s")[1]

    def head(self):
        return git(self.repo, "rev-parse", "HEAD")[1]

    def staged(self):
        return set(git(self.repo, "diff", "--cached", "--name-only")[1].split())


# --- THE REGRESSION: non-ASCII messages ----------------------------------------------------
# The em-dash alone does NOT reproduce it -- cp1252 happens to have 0x97 for U+2014, so a
# test written with only an em-dash passes against the broken code. The arrow (U+2192) has
# no cp1252 mapping and is what actually raised. Both are in every message this project
# writes, so both are in the fixture; keep the arrow or this test stops testing anything.
NON_ASCII = "subject — with an arrow → in it\n\nbody — more → prose\n"

with Sandbox() as s:
    s.write("a.txt", "one\n")
    rc, out, err = run_cv(s.repo, ["a.txt"], NON_ASCII)
    check("non-ASCII message commits (stdin route)", rc, 0)
    check("non-ASCII subject survives byte-for-byte",
          s.head_subject(), "subject — with an arrow → in it")
    check("nothing left staged after success", s.staged(), set())

with Sandbox() as s:
    s.write("a.txt", "one\n")
    msg = s.root / "msg.txt"
    msg.write_text(NON_ASCII, encoding="utf-8")
    rc, out, err = run_cv(s.repo, ["a.txt"], "", extra=["--message-file", str(msg)])
    check("non-ASCII via --message-file agrees with stdin", rc, 0)
    check("--message-file subject identical to stdin route",
          s.head_subject(), "subject — with an arrow → in it")

# --- THE SECOND REGRESSION: non-ASCII PATHS ------------------------------------------------
# Found 2026-07-29 while verifying the message fix above, and NOT covered by it: the encoding
# fix made git's output decode cleanly, but git still ESCAPED it. With core.quotepath at its
# default (true), any path byte >0x7f comes back as
#     "r\303\251sum\303\251-\342\206\222.txt"
# which never equals the path the caller passed, so POSTCONDITION 1 said "not staged" and
# POSTCONDITION 3 said "HEAD does not contain" about a file that was staged and did land in
# HEAD. Exit 1, false diagnosis, tree left staged -- the same half-done state by another route.
#
# This case is why the assertion below reads HEAD with quotepath EXPLICITLY off: asserting
# through the default would reproduce the bug inside the test and pass either way.
NON_ASCII_PATH = "résumé-→.txt"

with Sandbox() as s:
    s.write(NON_ASCII_PATH, "content\n")
    rc, out, err = run_cv(s.repo, [NON_ASCII_PATH], NON_ASCII)
    check("non-ASCII PATH commits (not just a non-ASCII message)", rc, 0)
    check("  ... and the postcondition did not falsely claim 'not staged'",
          "not staged" in err, False)
    in_head = git(s.repo, "-c", "core.quotepath=false",
                  "show", "--pretty=", "--name-only", "HEAD")[1]
    check("  ... and the path really is in HEAD, unescaped", in_head, NON_ASCII_PATH)
    check("  ... and nothing was left staged", s.staged(), set())


# --- REFUSALS. The load-bearing half. ------------------------------------------------------
# Each asserts BOTH a non-zero exit AND that HEAD did not move. Exit code alone would pass
# on a version that committed and then complained.

with Sandbox() as s:
    s.write("a.txt", "one\n")
    s.write("theirs.txt", "another agent's work\n")
    git(s.repo, "add", "theirs.txt")           # the concurrent-agent sweep
    before = s.head()
    rc, out, err = run_cv(s.repo, ["a.txt"], "should be refused → sweep\n")
    check("refuses a path staged by someone else", rc, 1)
    check("  ... and HEAD did not move", s.head(), before)
    check("  ... and the message names the recovery", "git restore --staged" in err, True)

with Sandbox() as s:
    s.write("a.txt", "one\n")
    s.write("theirs.txt", "another agent's work\n")
    git(s.repo, "add", "theirs.txt")
    rc, out, err = run_cv(s.repo, ["a.txt"], "allowed → through\n",
                          extra=["--allow-extra-staged"])
    check("--allow-extra-staged is the documented way past it", rc, 0)

with Sandbox() as s:
    before = s.head()
    rc, out, err = run_cv(s.repo, ["a.txt"], "no such path\n")
    check("refuses a path that does not exist", rc, 1)
    check("  ... and HEAD did not move", s.head(), before)

with Sandbox() as s:
    before = s.head()
    rc, out, err = run_cv(s.repo, ["seed.txt"], "nothing changed\n")
    check("refuses when every named path is unchanged", rc, 1)
    check("  ... and HEAD did not move", s.head(), before)

with Sandbox() as s:
    s.write("a.txt", "one\n")
    before = s.head()
    rc, out, err = run_cv(s.repo, ["a.txt"], "   \n\n  \n")
    check("refuses an empty message", rc, 1)
    check("  ... and HEAD did not move", s.head(), before)
    check("  ... and nothing was staged first", s.staged(), set())

# --- PUSH: the postcondition is origin == HEAD, not "push exited 0" ------------------------

with Sandbox() as s:
    s.write("a.txt", "one\n")
    rc, out, err = run_cv(s.repo, ["a.txt"], "pushed → upstream\n", push=True)
    check("--push succeeds against a real bare remote", rc, 0)
    check("  ... and origin/main really equals HEAD",
          git(s.repo, "rev-parse", "origin/main")[1], s.head())

with Sandbox() as s:
    s.write("a.txt", "one\n")
    git(s.repo, "remote", "set-url", "origin", str(s.root / "does-not-exist"))
    rc, out, err = run_cv(s.repo, ["a.txt"], "push will fail → loudly\n", push=True)
    check("a failing push is NOT reported as success", rc, 1)
    # The commit itself is allowed to stand -- the tool's contract is that it never
    # reports a success it did not achieve, not that it rewrites history on a push fault.
    check("  ... and it says so after having committed",
          s.head_subject(), "push will fail → loudly")

# --- POSITIVE CONTROL FOR THIS FILE --------------------------------------------------------
# If the sandbox or the invocation were broken, every "refuses" case above would pass for
# the wrong reason: a tool that cannot run at all also exits non-zero and leaves HEAD alone.
# So prove the rig can produce a SUCCESS, and prove a refusal's exit is distinguishable
# from a crash's.

with Sandbox() as s:
    s.write("a.txt", "one\n")
    rc, out, err = run_cv(s.repo, ["a.txt"], "plain ascii message\n")
    check("CONTROL: the rig can commit at all", rc, 0)
    check("CONTROL: success prints a confirmation", "committed" in out, True)
    check("CONTROL: success moved HEAD off the seed", s.head_subject(), "plain ascii message")

with Sandbox() as s:
    rc, out, err = run_cv(s.repo, [], "no paths\n")
    check("CONTROL: a refusal is exit 1, not a traceback", rc, 2)  # argparse: --path required
    check("CONTROL: argparse refusal is distinguishable from Failed(exit 1)",
          "Traceback" in err, False)


if FAILURES:
    print(f"FAIL ({len(FAILURES)}):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("commit_verify: all checks passed")
