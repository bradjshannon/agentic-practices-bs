# A `&&`-chained batch of CLI calls can silently drop every result but the first error's

**2026-08-25.** Four `note-find.py --resolve` calls chained with `&&` in one Bash invocation
produced one visible error and zero visible successes — and zero of the four actually landed.

## What happened

Four card-resolve commands were joined with `&&` in a single tool call, on the reasoning that
`&&` only stops at the *first failing* command, so anything before the failure should have already
run and printed its own success line. The tool result showed exactly one block of output: an
argparse-style error from the tool's own evidence-guard, for what looked like the fourth command
in the chain.

That reading was wrong. A follow-up `--list | grep` check showed **all four** cards still `open`
— including the ones that, by position, should have succeeded before the error-producing command
ever ran. The visible output did not tell you which commands executed; it told you what the last
line of stdout/stderr happened to be. Re-running each command individually (not chained) showed
three of the four succeed cleanly and one genuinely fail on the evidence-guard — the same defect
that was there in the chain, just now attributable to the right command.

## The rule

**A chained shell command's visible output is not proof of which links executed.** When a batch of
independent CLI calls is joined with `&&`/`;` in one tool call and the result shows fewer success
messages than commands, do not assume "everything before the visible error succeeded" — verify
independently (list/query the actual state) before trusting the partial-success narrative the
output seems to tell. This is distinct from the ordinary `&&`-semantics fact (it *does* stop at the
first failure) — the actual gap is that a harness/tool wrapper can truncate or reorder captured
output in a way that makes "ran and printed nothing" indistinguishable from "never ran."

## Why it generalises

Any agent batching several independent write operations (file edits, API calls, card resolves,
git operations) into one chained shell command inherits this same blind spot: the tool call's
result is not a reliable ledger of what happened, only of what was captured. The fix is cheap and
general — after any multi-command batch, re-derive the state independently (a `--list`, a `git
status`, a fresh read) rather than trusting the visible transcript, especially when the count of
visible success lines is fewer than the count of commands issued.
