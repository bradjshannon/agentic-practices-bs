# A mirror that rewrites the bytes it mirrors deleted a whole agent type, silently

**2026-08-01.** A sync tool copied a file from a repo onto the machine. Same content, same
size, no error. The agent type defined by that file **stopped existing** — it vanished from the
harness roster with no message anywhere.

## What happened

`conductor-sync.py` mirrors `~/.claude/agents/*.md` and a scheduled-task definition against a repo
copy. Its write was:

```python
dst.write_text(text, encoding="utf-8")
```

Python's default text mode **translates `\n` to `os.linesep` on write**. On Windows that is `\r\n`.
So every mirrored file was silently rewritten with CRLF endings.

`myproject-oracle.md` came back CRLF while every sibling agent definition was LF. The harness's
frontmatter parser stopped recognising it, and the agent type disappeared from the available list.
Nothing said so — no parse error, no warning, no log line. It was noticed only because a
system notice mentioned the type was no longer available.

Confirmed in both directions, which is what makes it a finding rather than a coincidence: the type
vanished when the file was CRLF, and the harness re-registered it within a turn of the file being
rewritten as LF.

## The rule

**A mirror must not change the bytes it is mirroring.** Open with `newline=""` (or write bytes) so
content lands exactly as read:

```python
with dst.open("w", encoding="utf-8", newline="") as fh:
    fh.write(text)
```

Any tool that copies, formats, normalises or "cleans" a file that another *program* parses is in
this class — sync tools, generators, linters with `--fix`, anything that round-trips through a text
API. A human diff shows nothing; a parser sees a different file.

## The second failure, which caused the first

The tool's flag is `--apply repo`, meaning **apply the repo's version onto the machine**. The
operator read it as "apply *to* the repo" and ran it in the destroying direction, overwriting two
files the tool had *just printed* as `machine is newer`.

**A destructive direction flag must not be ambiguous about which side is the source.** Better:
`--from repo` / `--from machine`, or refuse to overwrite a newer file without an explicit
`--overwrite-newer`. Printing "machine is newer" and then discarding it on a single ambiguous word
is a lying-affordance shape: the tool knows the answer and does not act on its own knowledge.

Related: `a-warning-you-can-ignore-is-not-a-control.md`,
`single-authority-not-mirrored-copies-2026-08-01.md`.
