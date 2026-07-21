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
