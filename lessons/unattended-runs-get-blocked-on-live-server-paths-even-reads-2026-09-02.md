# An unattended agent run can get blocked on a live-server command even when it's read-only

**Symptom:** A scheduled/unattended Claude Code session tries to SSH into a server it has
standing authorization to touch (a documented "standing grant," a prior human "go" recorded on
a decision-tracking surface). The command is refused outright: *"Permission for this action was
denied by the Claude Code auto mode classifier."* The session cannot find a config file, hook,
or setting anywhere in its own repos that implements this — because there isn't one to find.

**What actually happened:** This is Claude Code's own harness-level "auto mode" permission
classifier, evaluated per-tool-call, external to any repo the agent can read or edit. It fired
on three different command shapes in one session: `chmod` on a remote file, a `mysql ... UPDATE`
piped over stdin (not even a `-p<password>` CLI arg), and — the important data point — a plain
`cat` of a script under a server's `/bin` directory. That third one is pure read, no mutation at
all, and it was still blocked. So the trigger isn't "this command changes something"; it's closer
to "this command touches a live server's service/binary/config path at all." Read-only commands
that stayed in userland-ish territory (`tail`, `ls -la`, `stat`, `crontab -l`) all passed. The
denial message itself names the fix: a Bash permission rule added to Claude Code settings
*before* the run starts — which an unattended run cannot do for itself mid-session, and a prior
"go" recorded anywhere in a repo or on a status page does not satisfy it, because the classifier
has no visibility into that record at all.

**The rule:** Don't budget an unattended/scheduled agent run to apply *any* live-server-adjacent
SSH command, even ones you're certain are safe reads, and don't try to route around a refusal by
splitting it into smaller steps or changing its shape — that is explicitly against operating
instructions and the classifier's own guidance says so. Instead: verify what you can with the
commands that do pass (plain reads outside service/config paths usually do), write the exact
ready-to-run command down somewhere a human will see it, and treat the actual application of the
fix as work that needs an attended session — a human present, or a human who has pre-added the
specific permission rule to settings before kicking off the run.

**Why it generalises:** Any agent operating in "auto mode" / unattended on infrastructure it has
SSH access to will hit this, regardless of which estate or which server. The failure mode to
avoid is inferring, from one successful read-only SSH command, that the *next* one — even a
read — will also pass; the boundary is per-command and not obviously predictable from outside.
Budget unattended runs for **investigate + document + hand off a ready command**, not
**investigate + fix**, whenever the fix touches a live server's own files or services.
