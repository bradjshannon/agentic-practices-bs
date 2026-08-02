---
name: a-loud-instrument-is-not-data-either
description: A confident, plausible instrument reading (grep, mtime, diff, exit code) can be as wrong as silence — verify what it can't see before trusting it
---

# A loud instrument is not data either

**Symptom.** Four separate instrument readings in one session were confident, plausible, and
wrong: a `grep` for a call pattern undercounted because it assumed a one-line form; file mtimes
in a fresh git worktree read as "6 days newer" when they were actually checkout time, not edit
time; a naive `diff` reported "431 lines lost" when the real difference was a pure LF-vs-CRLF
line-ending split; a piped exit code silently read as `0` (success) when the real code was `3`
(a caught, structured failure). Two of these were one message away from becoming reported
findings that were flatly false — a merge that had "destroyed" an agent's own file, and a CI
run described as reporting green on a crash.

**What actually happened.** Each instrument produced real, non-empty output — so each one *looked*
alive and authoritative. The project already has a rule that an instrument's *silence* isn't
data (you have to know its heartbeat before trusting a null). This is the missing sibling: an
instrument's *loud answer* isn't data either, until you know what class of question it can and
cannot actually resolve. `grep` can't see multi-line call forms it wasn't written for. `mtime`
can't distinguish edit time from checkout time. A naive line-diff can't distinguish content
change from encoding change. A piped exit code silently becomes the pipe's own code, not the
command's.

**The rule.** Before using a cheap instrument (grep, mtime, a raw diff, an exit code read through
a pipe) as the sole evidence for a load-bearing claim — especially a negative-existence or
"this changed" claim — ask what that instrument structurally cannot see, and check that blind
spot specifically. If the claim is about content, read content, not proxies for it (checkout
time instead of edit time; line count instead of line *meaning*).

**Why it generalizes.** This isn't specific to any one tool. The pattern is: an instrument that
returns *something* reads as more trustworthy than one that returns nothing, precisely because it
looks like it did its job — but "did its job" and "answered the actual question" are different
claims, and only the second one matters. Apply the same skepticism to a loud green result that
you already apply to a quiet null one.
