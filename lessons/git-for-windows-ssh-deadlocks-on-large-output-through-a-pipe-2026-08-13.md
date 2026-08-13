# Git for Windows' `ssh`/`scp` deadlocks on large output through `subprocess.run(capture_output=True)` — 2026-08-13

## Symptom

A freshly-built, fully-tested Python script (56/56 unit tests green, all SSH/scp calls mocked)
hung to its own timeout on the very first live run against a real server. Not slow — the *exact*
timeout value every time (30s), on a command (`find ... -printf ...`) that returns in under a
second when run directly. The instinct is "the server is slow" or "the network is bad." Neither
was true: the identical command, run standalone in the same shell a few seconds later, returned
in well under a second.

## What actually happened

The script invoked `ssh`/`scp` via `subprocess.run(cmd, capture_output=True, ...)`. On this
machine (Windows, Git for Windows installed), `ssh`/`scp` resolve to Git's bundled MSYS-based
binaries (`C:\Program Files\Git\usr\bin\ssh.EXE`) — not Windows' native OpenSSH client.
`capture_output=True` makes Python create the child's stdout/stderr as Win32 anonymous pipes.
Isolated the variable directly: the same `ssh` invocation, same host, same command, hung every
time with `capture_output=True` (or an explicit `stdout=PIPE`), and completed in ~0.6s every time
when stdout/stderr were redirected to real `tempfile.TemporaryFile()` handles instead. Output
volume mattered — the triggering command returned 4.2 MB / 45,000 lines; a trivial command
(`echo ok`, `ssh -V`) through the same pipe path did not hang. The first hypothesis reached for
was stdin inheritance (the child inheriting a long-lived, never-closing parent stdin, common in
agent/harness environments) — tested independently with `stdin=subprocess.DEVNULL` and it made no
difference, ruling it out before spending more time on it. The actual mechanism is not fully
disassembled (leading theory: MSYS's own pipe/fd emulation layer not lining up cleanly with a
Win32 pipe handle created by a *native* Win32 process rather than another MSYS process), and
wasn't chased further, because the fix doesn't depend on knowing the exact internal reason.

## The rule

**On Windows, when invoking Git-for-Windows' bundled POSIX tools (`ssh`, `scp`, and likely others
in `Git\usr\bin\`) via `subprocess.run` where the output size isn't bounded and small, capture
stdout/stderr through real files, not pipes.** Concretely:

```python
import tempfile

def run_capturing_to_files(cmd: list[str], *, timeout: int) -> tuple[int, str, str]:
    with (
        tempfile.TemporaryFile(mode="w+b") as out_f,
        tempfile.TemporaryFile(mode="w+b") as err_f,
    ):
        result = subprocess.run(cmd, stdout=out_f, stderr=err_f, timeout=timeout)
        out_f.seek(0); err_f.seek(0)
        return result.returncode, out_f.read().decode("utf-8", "replace"), err_f.read().decode("utf-8", "replace")
```

Same external shape as `capture_output=True` (returncode, stdout, stderr as strings), so it's a
drop-in replacement at call sites. A command whose output is guaranteed tiny (a status check, a
single-line echo) is not at risk and doesn't need this — the cost only shows up once output grows
past whatever the pipe-buffer-sized regime is (observed: 1 MB triggers it reliably in a
regression test; a bare `echo` does not).

## Why it generalises

Any Windows-hosted Python tooling that shells out to Git-for-Windows' bundled `ssh`/`scp`/`rsync`
and expects non-trivial output — a directory listing, a `docker logs` dump, a file transfer with
verbose progress — is exposed to this, not just this one script. It is easy to ship clean because
**unit tests that mock the subprocess call cannot catch it** (the mock validates the call shape,
not that a real large-output child process actually returns through a real pipe), and a manual
smoke test with a trivial command (`ssh host echo ok`) also won't catch it, because small output
doesn't trigger the hang. The only way to catch it is either a live test against a command that
genuinely returns a lot of output, or — cheaper and portable — a regression test that runs *any*
subprocess (not necessarily `ssh` itself) producing output past the pipe-buffer-sized regime
through the actual capture function under test, which exercises the real code path without
needing a live server or the `ssh` binary. Before trusting a Windows ops script that shells out to
Git's POSIX tools and reports "all green" from mocked tests, ask whether it has ever actually run
against something that returns real volume.
