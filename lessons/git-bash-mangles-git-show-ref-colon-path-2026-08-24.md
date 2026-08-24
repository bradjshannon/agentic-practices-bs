# Git Bash silently mangles `git show <ref>:<path>` into a bad revision — 2026-08-24

## Symptom

`git -C <repo> show origin/main:some/file.yml` on Windows Git Bash (MSYS2) fails with
`fatal: bad revision 'origin\main;some\file.yml'` — a plausible-looking Git error that reads as
"that ref or path doesn't exist," when both are perfectly valid. A quieter variant: the same
command run through a pipe (`| grep ...`) can return **empty output with no error at all**, which
looks exactly like "the pattern isn't in the file" rather than "the command never ran against real
content."

## What actually happened

MSYS2's automatic path conversion — the same mechanism that turns `/c/Users/...` arguments into
`C:\Users\...` for native Windows programs — misfires on the `ref:path` colon syntax. It appears to
treat the argument as a Windows-style `PATH`-list value (colon → semicolon, forward slash →
backslash) rather than recognizing it as a single git revision spec, producing
`origin\main;some\file.yml` from `origin/main:some/file.yml`. The mangled string is neither a valid
ref nor a valid path, so git correctly reports it as a bad revision — but the *reported* value looks
like a typo the caller made, not like a shell-level rewrite, which sends debugging in the wrong
direction (double-checking the ref name and file path, both of which were actually correct).

## The rule

**On Windows Git Bash, prefix any `git show <ref>:<path>` (or similar colon-containing git
revision argument) with `MSYS_NO_PATHCONV=1`** to disable the auto-conversion for that command:
`MSYS_NO_PATHCONV=1 git show origin/main:path/to/file`. Do this every time this syntax is used from
Git Bash, not just when the plain form visibly errors — the pipe-through-grep variant fails
*silently* (empty match, not empty output with an explanit error), so a working-looking command
that returns nothing is not evidence the target doesn't exist.

## Why it generalises

Any git subcommand that takes a colon-separated `ref:path` argument (`git show`, `git cat-file
blob`, `git diff ref1:path ref2:path`) is vulnerable to the same misfire on Git Bash, and the
failure mode — a plausible "bad revision" for a genuinely valid ref, or silent emptiness through a
pipe — reads as evidence about the *repository* rather than about the *shell*, which is exactly the
inversion this project's own debugging guidance warns about (a negative search result closes one
search path, not the question). Before concluding a ref or path doesn't exist from a Git-Bash
`ref:path` command, re-run it with `MSYS_NO_PATHCONV=1` first.
