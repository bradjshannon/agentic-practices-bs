# A rediscovered-but-unapplied fix is a different failure than a missed one

**Symptom:** S3's backup-repo git clone has been stuck mid-rebase since 07-25, freezing its
heartbeat file and producing a false "backups are failing" HIGH audit finding every single night.
The fix is one command (`git reset --hard origin/main`, plus untracking two regenerating files so
the conflict doesn't recur), was scoped and offered on 07-28, and has since been *independently
re-discovered and re-carded seven more times* by different runs — each one correctly diagnosing
"backups are fine, it's the clone," each one filing a fresh card, none of them applying the fix
(it needs a destructive remote git op, correctly gated behind a human). By run 34 there were 8
open status-page cards, all cycling through variations of the same correct diagnosis.

**What actually happened:** the estate's usual failure modes are *missing* diagnosis (nobody
noticed) or *wrong* diagnosis (a false alarm accepted at face value). This is neither — every
single rediscovery got the diagnosis right. The failure is that a correct-but-gated fix, once
identified, gets filed with the same weight and the same wording as a brand-new finding, so
nothing in the system distinguishes "first time we've seen this" from "eighth time we've asked
the same person for the same one-line approval." A human scanning cards sees eight similar-looking
items and, reasonably, deprioritizes the pile rather than the specific stale one sitting at the
bottom of it.

**The rule:** before filing a card, check whether an open card already makes the same ask. If one
does, don't file a duplicate that says the same thing again — either (a) reply on the existing
thread with fresh evidence if you have any, or (b) if the finding has now recurred N times without
action, say so explicitly in the card itself ("this is the Nth time this has been offered, unfixed
since <date>") rather than filing it as if it were new. A rediscovery count is information the
human needs to correctly weight the ask; burying it in identical-looking cards throws that
information away.

**Why it generalises:** this is a corollary of the estate's own §6i (a dismiss is a verdict on the
card, not the topic) from the other direction — a *pile* of near-identical cards is itself a
signal quality problem, independent of whether any single card in the pile is well-evidenced. Any
system that lets an agent re-file the same finding without checking for an existing open thread
will eventually produce this shape: N technically-correct reports that collectively read as noise
because none of them says "this is not new." The fix is cheap (a search before filing) and the
cost of skipping it compounds — every silent duplicate makes the next duplicate feel more
normal, not less.
