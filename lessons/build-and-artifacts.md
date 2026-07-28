# Build and artifacts

## An artifact that was never built is not "designed" — it is unverified

*2026-07-21*

**Symptom.** A design spike produced a complete, carefully-reviewed container build: a
multi-stage build file, a build script, a pinned base image, and a thorough findings document
explaining the approach and its risks. It was treated as done-pending-rollout, blocked on
"we have no build host." When someone finally ran it, it **failed twice in a row** on two
independent defects — neither of which was subtle:

1. The documented build command tagged the image with a character the registry format forbids.
   The build was rejected before it started.
2. The build script's verification step composed a path incorrectly, doubling a directory
   prefix. The file it checked for could never exist, so the script aborted under
   `set -e` — *after* the compile it was verifying had actually succeeded.

Both were one-line fixes. Both had survived review because review reads code, and neither
defect is visible by reading — only by executing.

**What actually happened.** The blocker ("no build host") was itself false. The workstation had
no container runtime, so the spike concluded there was nowhere to build. But the *servers being
targeted* all ran a container runtime — they were, trivially, build hosts. The premise that
stopped anyone from running the build was never re-derived, so two latent defects sat in a
"finished" design for as long as the false blocker held.

**The rule.**

- **Run it once before calling a build design complete.** A build file that has never been
  executed is a hypothesis. Reviewers cannot catch invalid tags, path composition bugs, or
  environment assumptions; only the runtime can.
- **Re-derive the blocker before accepting it.** "We can't, because X" deserves one check that
  X is still true. Stale blockers hide finished work behind a wrong premise, and they get more
  expensive the longer they stand.
- Prefer **baking a patch into an immutable artifact** over re-applying it to running state.
  The failure that motivated this work was a live patch that any container recreate silently
  reverted; an image layer cannot be reverted by a restart.
- Verify the built artifact by **comparing it against known-good state** — file sizes, hashes,
  presence of markers — not by trusting that the build printed success.

**Why it generalises.** Every "we designed it but couldn't run it" artifact carries unknown
execution defects, and the count is rarely zero. The gap between reviewed and executed is where
this class of bug lives, and it is invisible in a diff.

---

## Author non-trivial file edits from a script file, not a shell heredoc (2026-07-26)

*2026-07-26*

**Symptom.** Three separate edits corrupted in one session. Two broke live tooling: one left a
status page unable to render, and one broke a `PreToolUse` hook that gates *every* shell call in
the session.

**What actually happened.** Each edit was applied with a Python one-liner inside a shell heredoc,
where the replacement text contained shell-significant characters. The shell interpreted them
before Python ever saw the string. In the worst case the replacement text mentioned `$'\r'` — the
ANSI-C quote for a carriage return — as *documentation of a bug*, and the shell helpfully expanded
it into a real newline, splitting a Python comment across two lines and producing
`SyntaxError: unterminated string literal` in the guard that every subsequent command had to pass.

The reflex fix is to escape more carefully. That is the wrong lesson: the same trap fired three
times *in a session where the agent already knew about it*.

**The rule.** For any edit whose replacement text contains quotes, backslashes, `$`, backticks or
newlines, **write a small script file and run it** — or use a structured edit tool. Do not pipe the
content through a shell. The shell is an interpreter you did not intend to invoke, and its
interpretation happens silently and before yours.

**Why it generalises.** This is the standard shape of "remove the path rather than police it." The
content most likely to be mangled is exactly the content that *documents* mangling — escape
sequences, regexes, quoting rules — so the failure concentrates in the commits explaining the
problem. And the blast radius is set by what you happened to be editing: a doc, or the guard
protecting the rest of the run.

---

## When a build resolves sources through an environment variable, reachability is the wrong question

*2026-07-28*

**Symptom.** A memory-sizing change was described as unshipped by a decision record, a handoff, a
status card, and the responsible engineer twice — while it was running in production on the
hardware. It had already caused an outage that nobody had connected to it.

**What actually happened.** Two repositories: one holds shared library sources, the other the
product that pins them by tag. The change landed in the library repo, on a commit **not** contained
in the pinned tag — so a tag-pinned build genuinely would not carry it. Separately, a
*build-plumbing* commit in the **product** repo widened an environment-variable override so more
components compiled from the library's live working tree instead of the pinned tag. From then on
the change shipped on every build.

No commit in the product repo changed any sizing. No commit in the library repo was ever
"deployed". **Each repository's history, read alone, is honest and incomplete** — so the standard
checks (`git log`, is-the-commit-an-ancestor, is-it-in-the-branch-we-ship-from) all *pass* while
being useless, because they answer *reachability in this history* and the question was *which tree
did the compiler actually read*.

**The rule.** Before believing anything is unshipped: check whether it is in the pinned reference
**and, separately, whether an override makes the pin irrelevant**. Most such build systems already
print which source won at configure time, and the deployed artifact usually reports its own source
revision and hash. Compare the running artifact's reported revision against the pin. In this case
the device had been reporting its true source revision the entire time and nobody compared it.

**Why it generalises.** Any "use my local checkout" escape hatch — a path override, a workspace
link, a vendored directory, a dev-mode resolver — silently converts a pinned dependency into a
live one, and does it from a commit that looks like plumbing. The blast radius of a change is then
invisible from either repository's log. Treat "not shipped yet" as a claim about the world that
rots, exactly like "still open" and "already fixed".
