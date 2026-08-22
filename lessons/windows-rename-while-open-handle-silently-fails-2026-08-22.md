# Windows silently refuses to rename a file while a handle to it is still open

**Symptom:** a durability primitive that writes to a `tmp` file then renames it into place
(write-tmp-then-rename, the standard atomic-durability pattern) works everywhere except native
Windows, where a reader/writer of the state file always sees the state reset to its default —
looked exactly like the *write* never happened, when it was actually the *rename* silently failing.

**What actually happened:** the code kept a `unique_ptr<IBlobStore>` (an open file handle) to the
tmp file alive across the call to rename it into place — a completely ordinary sequence on POSIX,
where renaming a file out from under an open file descriptor is explicitly permitted (the old name
is unlinked, the fd keeps working, the new name now points at the inode). Windows' rename semantics
are different: a handle opened without `FILE_SHARE_DELETE` (which `_sopen_s(..., _SH_DENYNO, ...)`
never requests) blocks a concurrent rename of that file. The rename call returned a real error code
(`ec=16`, "device or resource busy" on the reported system), but the caller didn't check it and
treated the file as durably written. Confirmed with a ~25-line minimal repro (below) isolated from
the actual codebase — same `_sopen_s`/`fs::rename` sequence, same failure while the handle is open,
same success immediately after `_close()`.

**The rule:** before porting or reviewing a write-tmp-then-rename durability pattern for Windows,
check explicitly that the tmp file's handle is closed (or opened with `FILE_SHARE_DELETE`) before
the rename call. Do not assume "it compiles and the test passes on Linux" proves the sequencing is
safe — this is exactly the kind of platform difference that a host-test suite built and mostly run
on WSL/Linux will never catch, and it will read as "the state occasionally resets," not as an
obvious crash.

**Why it generalises:** this is a property of the Windows filesystem API family
(`_sopen_s`/`CreateFile` without `FILE_SHARE_DELETE`), not of any one codebase — any cross-platform
C/C++ project doing atomic file writes via rename is exposed the same way. The original bug report
carried a *wrong* hypothesis for two rounds (an `_O_APPEND`/`_lseeki64` seek interaction) before
someone actually built a real Windows toolchain and reproduced the failure directly — the lesson
under that one: a plausible-sounding platform-specific hypothesis is not a substitute for compiling
and running the actual failing sequence on the actual platform.

**Minimal repro** (standalone, no project dependencies — needs an actual Windows CRT, e.g.
MinGW-w64/UCRT via `winget`, not WSL): `mechanisms/scripts/windows_rename_open_handle_repro.cpp` in
this repo. Compile and run directly; it prints the rename error code both while the handle is open
and after closing it.
