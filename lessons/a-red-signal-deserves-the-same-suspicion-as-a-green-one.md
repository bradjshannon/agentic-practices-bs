# A red signal deserves the same suspicion as a green one

## Symptom

A nightly backup job logged, every night for four days:

```
ERROR: backup repo rebase failed
ERROR: aborting before heartbeat update due to backup repo drift
```

The heartbeat file read `2026-07-25`. Two consecutive automated runs recorded "backups have not
completed since 07-25" as a live failure, raised it to the human, and planned around it. The human
replied "all clear" once; it was not clear, and the next run said so and re-raised it.

Nobody checked whether the backups were actually failing. **They were not.** Every night the job
dumped the database, uploaded to cloud storage, rotated old copies, captured logs, and pushed a
commit — all successfully. The remote's heartbeat file read **today's date**, and the remote carried
a daily backup commit for every day including the current one.

## What actually happened

The working clone on the server had diverged — one stray local commit, four behind. The backup
script does `git pull --rebase` *before* writing its heartbeat, that rebase failed against the
divergence, and the script aborted before the write.

So the **local** copy of the heartbeat file froze on 07-25 while the **real** one moved every night.
Three runs read the frozen local copy. The stray commit turned out to contain only regenerated log
files that the remote already had newer versions of.

The alarm was real, the log lines were accurate, and the conclusion drawn from them was wrong.

## The rule

**Apply the same scrutiny to bad news as to good news. Ask which copy of the artefact the check is
reading.**

Concretely, before accepting a failure signal:

- **Which instance did it measure?** A local mirror, a cache, a replica, a working copy — or the
  thing that actually matters?
- **What would be true elsewhere if the failure were real?** Here: the remote would be missing
  commits. It was not. That single question kills the wrong conclusion in one command.
- **Does the error message describe the failure, or a step adjacent to it?** "Aborting before
  heartbeat update" says the *bookkeeping* stopped. It never claimed the backup stopped. The
  inference from one to the other was ours.

## Why it generalises

The well-known failure is the false green: a status endpoint standing in for liveness, config
presence standing in for capability, a check that cannot run reporting nothing found. Whole
practices exist to distrust green.

**False reds are the same defect and get a fraction of the scrutiny**, for a reason worth naming:
*nobody audits bad news.* A green signal invites suspicion because it is convenient and someone will
be blamed if it is wrong. A red signal feels like diligence — you found a problem, you reported it,
you are being responsible. Challenging it feels like complacency, so it goes unchallenged and gets
inherited by whoever picks the work up next.

The cost compounds differently, too. A false green wastes attention that should have gone somewhere
else. A false red **spends** attention: three runs triaged it, one human was interrupted twice, and a
fix was drafted for a system that was working. It also crowds out the real defect — here, a diverged
clone that a one-line command resolves.

The tell is a signal that is *specific about a step* and *silent about the outcome*. "Aborting before
X" tells you X did not happen. It tells you nothing about the thing X was bookkeeping for.
