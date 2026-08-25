[//]: # (status: current)

# `subprocess.run()`'s output buffering looks identical to a hang, and costs real debugging time

**Symptom.** Launched a remote deploy script (`subprocess.run(ssh_cmd, capture_output=True,
timeout=1800)`), backgrounded via the harness's own bash-tool backgrounding. Fifteen-plus minutes
passed with zero new lines in the tool's output file. Two separate `ps -ef` checks on the remote
host, taken minutes apart, found no trace of the expected process tree (no `deploy.sh`, no
`docker`, no `sudo`). Both signals pointed the same direction: something was hung. Spent
significant time diagnosing a D-Bus/sudo-credential-caching theory before the command finally hit
its own 1800s timeout and confirmed a real (separate, also-real) bug — but the *initial* 15-minute
diagnosis window was built on a false premise.

**What actually happened.** `subprocess.run(..., capture_output=True)` calls
`Popen.communicate()`, which buffers **all** of stdout/stderr in memory and only returns it once
the process exits (or the timeout fires). Nothing is written to the harness's own progress file
until the whole call returns. So "the tool's output file hasn't changed in 15 minutes" is **not
evidence about the remote command** — it is a fixed property of this call shape, true whether the
remote side is stuck instantly or working perfectly for the full duration. Confirmed directly:
once the same command was relaunched with output redirected to a file on the *remote* host (`ssh
... 'cmd > logfile 2>&1 &' </dev/null`, polled independently), the real command produced correct
output within seconds and completed normally a few minutes later — it had never been the hang
candidate at all in that later run; the *original* invocation's problem turned out to be a
different, genuine bug (sudo credential caching not surviving a specific invocation shape), but
the 15 minutes spent suspecting a generic "it's hung" diagnosis, driven by the buffering artifact,
were not productive time toward finding that real bug.

**The two `ps -ef` misses compounded it.** A point-in-time process snapshot, taken twice, minutes
apart, is weak evidence of "nothing is happening" for any command whose real work is bursty
(brief CPU-active steps separated by longer I/O waits) — it can miss activity between polls just
as easily as it can catch a real hang. Neither signal alone, nor the two together, distinguished
"stuck" from "buffered and slow" with any real confidence.

**The rule.** Before treating "no new output for N minutes" from a `subprocess.run(...,
capture_output=True)`-style blocking call as evidence of a hang: know whether that call streams
output incrementally or buffers until completion. If it buffers (the common case for
`capture_output=True` / `stdout=PIPE` without incremental reads), silence proves nothing — the
call could be one second from finishing a legitimate multi-minute task. To get a real progress
signal, redirect the *remote or child* command's own output to a file and poll that file
independently of the wrapping call, or use a streaming read (`Popen` + incremental
`.stdout.readline()`) instead of `run(capture_output=True)`.

**Why it generalises.** This is not specific to SSH, deploy scripts, or this estate. Any tool call
that wraps a long-running command with the default buffered-`subprocess.run` shape will produce
this exact false signal on any host, in any project. The fix — redirect to a pollable file, or use
a streaming read — is the general answer, not a one-off workaround.
