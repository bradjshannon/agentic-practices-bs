# Backgrounding a command with shell `&` AND the tool's own `run_in_background` can spawn it twice

**Symptom.** A long-running command (a live eval hitting a real server, ~85 min expected) launched
via `command > logfile 2>&1 &` inside a Bash-tool call that also had `run_in_background: true` set.
The tool reported "completed" almost instantly. Checking the log showed a handful of lines and no
output file — read as "it failed fast." Relaunched with a corrected flag, same pattern: reused the
same `--out` path. Both runs eventually produced output to that path. The SLOWER (first, wrong-flag)
run's write landed second and silently clobbered the correct run's report — the file on disk showed
the first run's failure data, not the second run's success, with no error of any kind.

Checking running processes mid-investigation (`Get-CimInstance Win32_Process` on Windows, since the
Bash-tool's own `ps` did not see the processes) found **two distinct OS processes running the
identical command with identical arguments** — one via the intended venv interpreter, one via a
different, bare Python install found earlier on PATH. Root mechanism not fully explained (plausibly
the trailing `&` backgrounds a shell-level job that the tool's own `run_in_background` tracking
*also* tries to background/re-launch, producing two independent process trees instead of one), but
the observable shape was unambiguous and reproduced identically on both launches.

**What actually happened, in order.** (1) Launched with a trailing `&` inside a
`run_in_background: true` call — belt-and-suspenders backgrounding, seemed harmless. (2) Tool
reported the wrapper command "completed" — true only for the immediate shell return from
backgrounding, not for the actual long-running process, which was silently still running past that
report. (3) Checked too early, saw no output, concluded (wrongly) that the run had failed and
finished. (4) Relaunched with a fix, reusing the same `--out` path — no reason yet to suspect the
first attempt was still alive. (5) Both processes eventually wrote to the same file; last-write-wins
silently, with no lock, no conflict error, nothing that would flag a problem. (6) Only noticed by
independently checking OS process state, which nothing in the immediate task prompted — it was
caught by chance while investigating unrelated-looking early output.

**The rule.**

1. **Never combine a shell-level `&` with a tool's own backgrounding flag.** Pick exactly one
   mechanism. If the tool has a `run_in_background` option, use *only* that — no trailing `&`
   inside the command string.
2. **A "completed" report on a backgrounded wrapper is not proof the underlying long-running
   process finished** — it can be a report about the wrapper's own immediate return. If a command
   is expected to take real time, treat "no output yet" as "still running," not "must have failed,"
   and wait for the actual completion signal (a notification, a stable/growing log with no further
   change) rather than checking once early and concluding.
3. **Never reuse an output path across a relaunch of the same command without confirming the prior
   attempt is actually dead first.** A stale process racing a corrected one, both writing to the
   same file, produces silent data corruption with no error surface at all — the file looks
   completely normal, just wrong. Check for a lingering process by command line (not just tool
   name) before relaunching, and use a fresh, uniquely-named output path per attempt regardless.
4. **When a "fast completion" is unexpected for the kind of work being done, verify against
   process state, not just tool-reported status.** A tool's own completion bookkeeping and the OS's
   actual process table are two different sources of truth; they can and did disagree here.

**Why it generalizes.** Any harness offering both a shell backgrounding primitive (`&`, `nohup`)
and its own async/background execution mode has this exact double-backgrounding trap available —
it is a property of composing two independent backgrounding mechanisms, not specific to this one
task or server. The output-path-race half of the lesson generalizes further still: any two
processes (accidental duplicates or two genuinely different jobs) writing to the same file with no
locking will silently corrupt via last-write-wins, regardless of what backgrounding mechanism
produced them.
