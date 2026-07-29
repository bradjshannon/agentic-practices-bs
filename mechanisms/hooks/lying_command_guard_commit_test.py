"""Both directions for the `git commit` -> commit_verify.py rule.

Loads the guard **relative to this file**, i.e. THIS REPO'S copy -- not
`~/.claude/hooks/`. The two older lying_command_guard suites do the latter, which means
a machine could pull a broken banked hook and still get a green run. `evidence_with_claim_test.py`
and `data_validity_statement_test.py` already load relative; this follows those.

Run:  py -3 mechanisms/hooks/lying_command_guard_commit_test.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("g", HERE / "lying_command_guard.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

# The rule only fires where commit_verify.py is resolvable, so pin the resolver instead
# of depending on this machine's layout. The "not resolvable" branch is a CASE below --
# it is the branch that would otherwise never be demonstrated.
FAKE = "/x/commit_verify.py"
g.commit_verify_path = lambda: FAKE

Q = chr(34)


def fired(cmd: str) -> bool:
    return any("Raw `git commit`" in p for p, _ in g.check(cmd))


CASES = [
    # --- MUST FIRE: shapes that really create (or fail to create) a commit ------------
    ("FIRE  bare commit with a message",
     f"git commit -m {Q}fix: the thing{Q}", True),
    ("FIRE  git -C <path> commit",
     "git commit -m x".replace("git", "git -C /repo", 1), True),
    ("FIRE  git -C with a QUOTED path containing a space",
     f"git -C {Q}C:/Users/x/My Repo{Q} commit -F msg.txt", True),
    ("FIRE  commit at the end of a compound",
     "cd /repo && git add file.py && git commit --no-verify -m x", True),
    ("FIRE  commit inside a nested shell payload",
     f"bash -c {Q}git commit -m wip{Q}", True),
    ("FIRE  commit with a global -c option before the subcommand",
     "git -c user.name=bot commit -m x", True),

    # --- must NOT fire: read commands whose text contains `commit` --------------------
    ("quiet  git log", "git log --oneline -5", False),
    ("quiet  git show", "git show --stat HEAD", False),
    ("quiet  git status", "git status --short", False),
    ("quiet  git commit-graph (substring trap, the app-flash shape)",
     "git commit-graph write --reachable", False),
    ("quiet  git commit-tree (substring trap)",
     "git commit-tree HEAD^{tree} -m x", False),
    ("quiet  git log --grep=commit (value, not subcommand)",
     "git log --grep=commit --oneline", False),
    ("quiet  git rev-parse", "git rev-parse HEAD", False),
    ("quiet  git diff --cached", "git diff --cached --name-only", False),

    # --- must NOT fire: legitimate or inexpressible cases ----------------------------
    ("quiet  --amend (commit_verify cannot express it, so nothing to recommend)",
     f"git commit --amend --no-edit", False),
    ("quiet  bare push is NOT blocked (work may have been committed earlier)",
     "git push origin main", False),
    ("quiet  the word commit inside quoted DATA",
     f"echo {Q}never run git commit directly{Q} >> notes.md", False),
    ("quiet  commit_verify.py itself is exempt",
     "python /x/commit_verify.py --repo /r --path a.py --push", False),
    ("quiet  a non-git program whose name contains commit",
     "python tools/commit-linter.py --check", False),
]

bad = 0
for name, cmd, want in CASES:
    got = fired(cmd)
    ok = got == want
    bad += not ok
    print(f"{'PASS' if ok else 'FAIL':4} | fired={str(got):5} want={str(want):5} | {name}")
    if not ok:
        for prob, fix in g.check(cmd):
            print("        ->", prob[:90])

# --- the reachability gate, both ways --------------------------------------------------
# A repo/machine where commit_verify.py does not exist must pass a commit straight
# through: a block that names a command the machine does not have converts one wrong
# turn into two, which is this file's stated rule.
g.commit_verify_path = lambda: None
unreachable = fired("git commit -m x")
print(f"{'PASS' if not unreachable else 'FAIL':4} | fired={str(unreachable):5} want=False "
      "| quiet  commit_verify.py NOT reachable -> no block")
bad += unreachable

g.commit_verify_path = lambda: FAKE
# The block must NAME the script and the real flag syntax, or it teaches the wrong command.
text = " ".join(fix for _, fix in g.check("git -C /repo commit -m x"))
for needle in (FAKE, "--repo /repo", "--path", "--push", "guard:ok"):
    ok = needle in text
    bad += not ok
    print(f"{'PASS' if ok else 'FAIL':4} | block text names {needle!r}")

# The first LIVE block printed `--repo Q` -- the quote placeholder leaked into the
# message. A block naming a command with a wrong argument is worse than no block, so
# the quoted-path form gets its own assertion.
text = " ".join(fix for _, fix in g.check(f"git -C {Q}C:/Users/x/My Repo{Q} commit -m x"))
for needle in ("--repo C:/Users/x/My Repo",):
    ok = needle in text
    bad += not ok
    print(f"{'PASS' if ok else 'FAIL':4} | block text names {needle!r}")

print()
print("ALL CORRECT" if not bad else f"{bad} WRONG")
sys.exit(1 if bad else 0)
