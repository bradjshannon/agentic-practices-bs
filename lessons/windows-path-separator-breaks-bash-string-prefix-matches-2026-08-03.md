# A Windows `Path` breaks a bash string-prefix match, and the fix looks broken instead — 2026-08-03

## Symptom

A new test suite for a bash function (extract the function's source, run it via `subprocess.run(["bash",
"-c", script])` against a scratch directory tree built with `pathlib`) had exactly the shape expected:
the "should pass" cases passed, and the "should fail" cases also reported success — the function
never found anything wrong, on inputs deliberately constructed to be wrong. The instinct this
produces is "the fix doesn't work" or "the test doesn't exercise the fix." Neither was true.

## What actually happened

The bash function does a plain string-prefix comparison: `[[ "$host_path" != "$CUSTOM_DIR"/* ]]`.
On Windows, `pathlib.Path.__str__()` renders with backslashes (`C:\Users\...\compose_dir\custom`).
The test harness passed that string straight into the injected `CUSTOM_DIR` variable. Separately,
the bash function itself builds `host_path` by resolving a relative compose path against
`COMPOSE_DIR` with an **explicit forward slash** it writes itself: `host_path="$COMPOSE_DIR/custom/..."`.
So `CUSTOM_DIR` arrived as `...\compose_dir\custom` while `host_path` was constructed as
`...\compose_dir/custom/...` — identical on disk, byte-different as strings, at exactly the
separator between the two path segments.

Filesystem tests (`[ -d "$host_path" ]`, `find`) worked fine throughout, because Windows/Git-Bash
file I/O tolerates mixed separators. Only the **pure string comparison** — which does not touch the
filesystem at all — silently failed, causing the function to `continue` past every mount under test
without ever reaching its validation logic. Every "should fail" case produced a false pass because
nothing was ever checked, not because the check ran and approved.

## The rule

**When a test harness bridges two languages that disagree about path separators (Python's
`pathlib` and a POSIX shell script), normalize to one separator before either side sees the value —
don't let each side build its own.** `Path.as_posix()` on the Python side, used everywhere a path
crosses into the injected script, removes the disagreement entirely. Filesystem operations will not
tell you this is wrong, because they don't care about separators; only a same-string equality or
prefix check will, and by the time you're looking at that check's *result* the actual mismatch is
one abstraction layer removed from what's in front of you.

## Why it generalises

Any cross-language test harness that interpolates a host-language path into a target-language
string is vulnerable to this, not just Python-into-bash: the target language's own path-building
convention (forward slash, backslash, or a path-join function) can silently diverge from whatever
string the host language handed it, and the resulting bug presents as **the code under test
appearing to do nothing** — the false-negative shape that's hardest to distinguish from "the fix
doesn't do anything," because both look identical from the test's assertions. Before concluding a
fix under test is inert, check whether every path that crosses the language boundary was normalized
to one separator convention on the way across.
