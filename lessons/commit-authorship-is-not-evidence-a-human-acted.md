# Commit authorship is not evidence a human acted — and "no open lock" is not evidence you are alone

## Symptom

A scheduled agent (a "conductor" that owns one project domain for a run) started, ran its preflight,
and saw `collab log: no open session`. It concluded it was the only agent working that domain.

Over the next hour it noticed new commits appearing on `main` that it had not made. It ran
`git log -1 --format=%an`, read **the user's own name**, and stated as fact — in chat, in a reply to
the user, and in a card it marked resolved — *"That's Brad himself; he read the card and did the
thing."* It built follow-on work on that reading.

The user corrected it: *"anything you've attributed to me that was done in over the last 7 hours was
actually done by another instance of the server conductor."*

## Two independent failures, and they compounded

**1. `%an` cannot distinguish an agent from its user.** Every agent in that setup committed through
the user's global `.gitconfig`, so *every* commit — human or agent — was authored `Brad Shannon`.
The field the agent used as an identity check had exactly one possible value. It was not a weak
signal; it was **no signal**, and it read as a strong one because it named a specific person.

**2. The concurrency check answered a question whose answer was usually "no".** Detection was "does
the collaboration log show an open row?" — but an agent holds an open row only while it is
*mid-write*. A sibling that is reading, thinking, or between actions is invisible. So a clean
preflight *looked* like proof of solitude while a sibling was live and pushing.

Compounded, they were worse than either alone: the concurrency check said "you are alone", and the
authorship check said "a human did that" — two independent-looking confirmations of one wrong model,
both derived from instruments that could not have said otherwise.

## The general shape

**An instrument with one possible output is not a measurement.** Ask of any check: *what reading
would falsify what I am about to conclude?* If none exists, you have a ritual.

- `%an` when every commit is authored identically → cannot indicate a human.
- "Is a lock held?" when the lock is taken only during writes → cannot indicate solitude.

And the corollary that made it expensive: **presence must be something a participant TAKES, not
something inferred from what it happens to be doing at the instant you look.** Absence-of-activity
and absence-of-participant are the same observation.

## The fix, and why each part is load-bearing

**A lease, not a check.** Acquired at start, refused to a second holder, so occupancy is the default
state of a running agent rather than a side effect of its current activity.

- **Heartbeat expiry, not a PID.** An agent has no stable OS process — its shell dies between tool
  calls. Liveness is a timestamp the holder refreshes. A crashed run's lease then expires by itself;
  the cost is one skipped scheduled tick, which is nothing.
- **A local file, not a repo file.** Both agents ran on one workstation. A repo file needs a push to
  become visible and races on exactly the boundary it protects.
- **Normalise the holder identity.** The launcher passed `D:\path\...`; a hand-run passed
  `D:/path/...`. Compared raw, an agent fails to renew *its own* lease, then reads **itself** as a
  live sibling and stands down. Found by a test, before it bit a real run.
- **Refuse to release a lease you do not hold.** Otherwise "cleanup" becomes the thing that creates
  the concurrency.

**Name the author.** Set a per-*worktree* `user.name` so commits read `<Role> (<worktree>)`.

- **Leave `user.email` alone.** Forges link commits to accounts by email; rewriting it costs the
  contribution graph and mention-linking to buy nothing, because `%an` is the field that is printed.
- **Scope matters more than the setting.** Where the agent has its own worktree, a per-worktree
  write is safe. Where it shares a clone with the human — as a sibling agent in the same setup did —
  a persistent write would relabel **the human's own commits as the agent's**, which is worse than
  the original problem. The convention generalises; the mechanism only generalises where the agent
  is isolated. That asymmetry is easy to miss when rolling a fix out "everywhere".

## Verify the guard by breaking it

Replacing a guard that could not detect a sibling with an *untested* guard is the same mistake in
newer clothes. Each test should name the failure it catches, and the suite should be proven by
mutation rather than by passing:

- remove the holder normalisation → only the path tests fail
- make the "sibling holds it" branch unreachable → the refusal tests fail across every class
- degrade worktree scope to repo-wide → the "the human's own commits stay theirs" test fails

That last one is the test that decides whether the fix can be adopted in a shared clone at all.

## The transferable line

**Before crediting a person with an action, ask what your evidence could not have said.** Metadata
carrying a human's name is not testimony that a human was there — it is a default, and defaults are
the easiest thing in a system to mistake for observations.
